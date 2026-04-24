"""
Gemini Vision OCR service.

Extracts text from field images (handwritten forms, WhatsApp screenshots,
printed survey sheets) and returns structured JSON.

Confidence scoring logic:
  - Gemini doesn't return explicit confidence scores, so we derive one from:
    1. Whether the model populated all expected fields vs returned nulls/empty
    2. Presence of low-confidence markers in the text (e.g. "[illegible]")
    3. Response parse success (failed parse → confidence 0.0)
  - confidence < LOW_CONFIDENCE_THRESHOLD → needs_review = True
"""

import json
import logging
import os
import re
import time
from base64 import b64encode

import httpx

logger = logging.getLogger(__name__)

LOW_CONFIDENCE_THRESHOLD = 0.6
GEMINI_TIMEOUT_S = 10.0
GEMINI_RETRIES = 1

# ── System prompt ─────────────────────────────────────────────────────────────
# Tight constraints: JSON only, no prose, explicit schema, illegibility markers.
EXTRACTION_SYSTEM_PROMPT = """You are an OCR specialist for disaster-relief field forms.
Extract ALL readable text from the image and return ONLY valid JSON. No prose, no markdown, no explanation.

Return this exact schema:
{
  "extracted_text": "<full verbatim text readable in the image, preserving line breaks as \\n>",
  "language_detected": "<ISO 639-1 code: en | hi | bn | mr | te | ta | or unknown>",
  "text_regions": [
    {
      "label": "<what this region appears to be: title | field_label | field_value | handwritten_note | printed_text | signature | date>",
      "content": "<text in this region>",
      "legible": <true | false>
    }
  ],
  "illegible_regions_count": <integer, count of regions where text could not be read>,
  "image_quality": "<clear | moderate | poor | unreadable>",
  "confidence_indicators": {
    "is_blurry": <true | false>,
    "is_low_light": <true | false>,
    "is_handwritten": <true | false>,
    "is_printed": <true | false>,
    "partial_occlusion": <true | false>
  }
}

Rules:
- extracted_text must contain every readable word. Do not summarise.
- For illegible words write [illegible] in place of the word.
- If the entire image is unreadable, set extracted_text to "" and image_quality to "unreadable".
- NEVER invent or guess text that is not visible. Only transcribe what you can see.
- Return ONLY the JSON object. No other characters before or after."""


class OCRResult:
    def __init__(
        self,
        extracted_text: str,
        confidence: float,
        needs_review: bool,
        language: str,
        image_quality: str,
        text_regions: list[dict],
        illegible_count: int,
        confidence_indicators: dict,
        raw_response: str,
    ):
        self.extracted_text = extracted_text
        self.confidence = confidence
        self.needs_review = needs_review
        self.language = language
        self.image_quality = image_quality
        self.text_regions = text_regions
        self.illegible_count = illegible_count
        self.confidence_indicators = confidence_indicators
        self.raw_response = raw_response

    def dict(self):
        return {
            "extracted_text": self.extracted_text,
            "confidence": round(self.confidence, 3),
            "needs_review": self.needs_review,
            "language_detected": self.language,
            "image_quality": self.image_quality,
            "text_regions": self.text_regions,
            "illegible_regions_count": self.illegible_count,
            "confidence_indicators": self.confidence_indicators,
        }


async def extract_text_from_image(
    image_bytes: bytes,
    mime_type: str,
) -> OCRResult:
    """
    Send image to Gemini Vision and extract structured text.
    Retries once on timeout/parse failure, then returns needs_review=True.
    """
    from app.core.config import settings
    api_key = settings.GEMINI_API_KEY
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY not set")

    last_error = None
    for attempt in range(GEMINI_RETRIES + 1):
        try:
            raw = await _call_gemini(image_bytes, mime_type, api_key)
            return _parse_response(raw)
        except (httpx.TimeoutException, httpx.HTTPStatusError) as e:
            last_error = e
            logger.warning(f"Gemini attempt {attempt + 1} failed: {e}")
            if attempt < GEMINI_RETRIES:
                continue
        except json.JSONDecodeError as e:
            last_error = e
            logger.warning(f"Gemini JSON parse failed attempt {attempt + 1}: {e}")
            if attempt < GEMINI_RETRIES:
                continue

    # All retries exhausted → flag for manual review
    logger.error(f"Gemini OCR failed after {GEMINI_RETRIES + 1} attempts: {last_error}")
    return _manual_review_fallback(str(last_error))


async def _call_gemini(image_bytes: bytes, mime_type: str, api_key: str) -> str:
    """POST to Gemini 1.5 Pro vision endpoint."""
    image_b64 = b64encode(image_bytes).decode()

    payload = {
        "system_instruction": {
            "parts": [{"text": EXTRACTION_SYSTEM_PROMPT}]
        },
        "contents": [
            {
                "role": "user",
                "parts": [
                    {
                        "inline_data": {
                            "mime_type": mime_type,
                            "data": image_b64,
                        }
                    },
                    {"text": "Extract all text from this field form image."},
                ],
            }
        ],
        "generationConfig": {
            "temperature": 0.0,       # deterministic
            "topP": 1,
            "topK": 1,
            "maxOutputTokens": 2048,
            "responseMimeType": "application/json",  # Gemini JSON mode
        },
    }

    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"gemini-1.5-pro:generateContent?key={api_key}"
    )

    async with httpx.AsyncClient(timeout=GEMINI_TIMEOUT_S) as client:
        resp = await client.post(url, json=payload)
        resp.raise_for_status()

    data = resp.json()

    # Extract text from Gemini response structure
    try:
        raw_text = data["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError) as e:
        raise ValueError(f"Unexpected Gemini response shape: {e}\n{data}")

    return raw_text


def _parse_response(raw: str) -> OCRResult:
    """Parse Gemini JSON output and derive confidence score."""
    # Strip any accidental markdown fences Gemini sometimes adds despite instructions
    cleaned = re.sub(r"^```(?:json)?\s*", "", raw.strip())
    cleaned = re.sub(r"\s*```$", "", cleaned)

    parsed = json.loads(cleaned)  # raises JSONDecodeError → triggers retry

    extracted_text: str = parsed.get("extracted_text", "")
    language: str = parsed.get("language_detected", "unknown")
    image_quality: str = parsed.get("image_quality", "unknown")
    text_regions: list = parsed.get("text_regions", [])
    illegible_count: int = parsed.get("illegible_regions_count", 0)
    ci: dict = parsed.get("confidence_indicators", {})

    confidence = _derive_confidence(
        extracted_text=extracted_text,
        image_quality=image_quality,
        illegible_count=illegible_count,
        text_regions=text_regions,
        confidence_indicators=ci,
    )

    needs_review = (
        confidence < LOW_CONFIDENCE_THRESHOLD
        or image_quality in ("poor", "unreadable")
        or illegible_count > 2
    )

    return OCRResult(
        extracted_text=extracted_text,
        confidence=confidence,
        needs_review=needs_review,
        language=language,
        image_quality=image_quality,
        text_regions=text_regions,
        illegible_count=illegible_count,
        confidence_indicators=ci,
        raw_response=raw,
    )


def _derive_confidence(
    extracted_text: str,
    image_quality: str,
    illegible_count: int,
    text_regions: list,
    confidence_indicators: dict,
) -> float:
    """
    Heuristic confidence score 0.0–1.0.
    Gemini doesn't expose token logprobs, so we score from output signals.
    """
    score = 1.0

    # Image quality penalty
    quality_penalty = {"clear": 0.0, "moderate": 0.1, "poor": 0.35, "unreadable": 1.0}
    score -= quality_penalty.get(image_quality, 0.2)

    # Illegible regions penalty (each costs 0.1, capped at 0.4)
    score -= min(illegible_count * 0.10, 0.40)

    # [illegible] markers in text
    illegible_marker_count = extracted_text.lower().count("[illegible]")
    score -= min(illegible_marker_count * 0.05, 0.25)

    # Empty extraction
    if not extracted_text.strip():
        score -= 0.5

    # Confidence indicator penalties
    if confidence_indicators.get("is_blurry"):
        score -= 0.15
    if confidence_indicators.get("is_low_light"):
        score -= 0.10
    if confidence_indicators.get("partial_occlusion"):
        score -= 0.20

    # Bonus: handwritten is harder, but if we got regions it means we succeeded
    if confidence_indicators.get("is_handwritten") and len(text_regions) > 0:
        score += 0.05  # slight bump for successfully parsing handwriting

    return max(0.0, min(1.0, score))


def _manual_review_fallback(error_detail: str) -> OCRResult:
    """Return a safe fallback result when all retries fail."""
    return OCRResult(
        extracted_text="",
        confidence=0.0,
        needs_review=True,
        language="unknown",
        image_quality="unknown",
        text_regions=[],
        illegible_count=0,
        confidence_indicators={},
        raw_response=f"ERROR: {error_detail}",
    )