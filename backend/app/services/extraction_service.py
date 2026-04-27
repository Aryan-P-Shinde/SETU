"""
LLM extraction service — text → structured NeedCard fields.

All three intake channels funnel here:
  voice  → transcript string  ──┐
  image  → extracted_text     ──┼──► extract_need_fields() ──► ExtractionResult
  text   → raw text           ──┘

Design decisions:
  - Prompt is loaded from prompts/ dir (version-controlled, swappable)
  - Pydantic validates the JSON response; retry once on parse failure
  - On two consecutive failures: store raw input, set extraction_failed=True
  - Chain-of-thought (urgency_reasoning) is preserved in output for NGO audit
  - Source channel is tracked for downstream dedup and analytics
"""

import json
import logging
import os
import re
from enum import Enum
from pathlib import Path
from typing import Optional

import httpx
from pydantic import BaseModel, Field, field_validator, model_validator

logger = logging.getLogger(__name__)

GEMINI_TIMEOUT_S = 15.0
EXTRACTION_RETRIES = 3
PROMPTS_DIR = Path(__file__).parent.parent / "prompts"


# ── Enums ─────────────────────────────────────────────────────────────────────

class NeedType(str, Enum):
    medical   = "medical"
    food      = "food"
    shelter   = "shelter"
    water     = "water"
    rescue    = "rescue"
    logistics = "logistics"
    other     = "other"


class SourceChannel(str, Enum):
    voice  = "voice"
    image  = "image"
    text   = "text"


CANONICAL_SKILLS = {
    "medical_first_aid", "medical_doctor", "medical_nurse", "medical_paramedic",
    "food_distribution", "food_cooking", "water_purification", "water_distribution",
    "search_rescue", "structural_assessment", "debris_clearance",
    "mental_health_counseling", "child_care", "elderly_care",
    "logistics_driver", "logistics_boat_operator", "logistics_coordination",
    "translation_hindi", "translation_bengali", "translation_telugu",
    "translation_tamil", "translation_marathi",
    "engineering_civil", "engineering_electrical", "legal_aid", "communications",
}


# ── Pydantic response model ───────────────────────────────────────────────────

class ExtractionResult(BaseModel):
    need_type: NeedType
    description_clean: str = Field(min_length=5)
    urgency_reasoning: str = Field(min_length=10)
    urgency_score: float = Field(ge=0.0, le=10.0)
    affected_count: Optional[int] = Field(default=None, ge=1)
    skills_needed: list[str] = Field(default_factory=list)
    location_text: str = ""
    contact_name: Optional[str] = None
    contact_detail: Optional[str] = None

    # ── Extraction metadata (not from LLM, added by service) ─────────────────
    source_channel: SourceChannel = SourceChannel.text
    raw_input: str = ""
    extraction_failed: bool = False
    prompt_version: str = "v1"

    @field_validator("urgency_score", mode="before")
    @classmethod
    def round_urgency(cls, v):
        return round(float(v), 1)

    @field_validator("skills_needed", mode="before")
    @classmethod
    def validate_skills(cls, v):
        if not isinstance(v, list):
            return []
        # Keep only canonical skills; log unknowns but don't fail
        valid = []
        for skill in v:
            if skill in CANONICAL_SKILLS:
                valid.append(skill)
            else:
                logger.warning(f"Non-canonical skill dropped: {skill!r}")
        return valid

    @field_validator("affected_count", mode="before")
    @classmethod
    def coerce_affected_count(cls, v):
        if v is None:
            return None
        try:
            n = int(v)
            return n if n > 0 else None
        except (TypeError, ValueError):
            return None

    @field_validator("contact_detail", "contact_name", mode="before")
    @classmethod
    def empty_string_to_none(cls, v):
        if v == "" or v == "null":
            return None
        return v

    def dict_for_needcard(self) -> dict:
        """Return fields ready to merge into a NeedCard document."""
        return {
            "need_type": self.need_type.value,
            "description_clean": self.description_clean,
            "urgency_reasoning": self.urgency_reasoning,
            "urgency_score_base": self.urgency_score,
            "affected_count": self.affected_count,
            "skills_needed": self.skills_needed,
            "location_text_raw": self.location_text,
            "contact_name": self.contact_name,
            "contact_detail": self.contact_detail,
            "source_channel": self.source_channel.value,
            "extraction_failed": self.extraction_failed,
            "prompt_version": self.prompt_version,
        }


# ── Prompt loading ────────────────────────────────────────────────────────────

def _load_prompt(version: str = "v1") -> str:
    path = PROMPTS_DIR / f"extraction_{version}.txt"
    if not path.exists():
        raise FileNotFoundError(f"Prompt not found: {path}")
    return path.read_text(encoding="utf-8")


# ── Main entry point ──────────────────────────────────────────────────────────

async def extract_need_fields(
    raw_text: str,
    source_channel: SourceChannel = SourceChannel.text,
    prompt_version: str = "v1",
) -> ExtractionResult:
    """
    Extract structured NeedCard fields from raw text (any channel).
    Retries once on parse failure; returns extraction_failed=True fallback
    if both attempts fail.
    """
    if not raw_text or not raw_text.strip():
        return _failed_extraction("Empty input text", raw_text, source_channel, prompt_version)

    from app.core.config import settings
    api_key = settings.GEMINI_API_KEY
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY not set")

    try:
        system_prompt = _load_prompt(prompt_version)
    except FileNotFoundError as e:
        raise RuntimeError(str(e))

    last_error = None
    for attempt in range(EXTRACTION_RETRIES + 1):
        try:
            raw_json = await _call_gemini(raw_text, system_prompt, api_key)
            result = _parse_and_validate(raw_json, source_channel, raw_text, prompt_version)
            return result
        except httpx.HTTPStatusError as e:
            last_error = e
            logger.warning(f"Extraction attempt {attempt + 1} API error: {e}")
            if e.response.status_code == 429:
                # Try Groq fallback immediately on rate limit
                groq_result = await _try_groq_fallback(raw_text, system_prompt, source_channel, prompt_version)
                if groq_result:
                    return groq_result
                wait = 15 * (attempt + 1)
                logger.info(f"Rate limited — waiting {wait}s before retry...")
                import asyncio
                await asyncio.sleep(wait)
        except httpx.TimeoutException as e:
            last_error = e
            logger.warning(f"Extraction attempt {attempt + 1} timeout: {e}")
        except (json.JSONDecodeError, ValueError) as e:
            last_error = e
            logger.warning(f"Extraction attempt {attempt + 1} parse error: {e}")
        except Exception as e:  # noqa: BLE001
            last_error = e
            logger.warning(f"Extraction attempt {attempt + 1} unexpected error: {e}")

    logger.error(f"Extraction failed after {EXTRACTION_RETRIES + 1} attempts: {last_error}")
    return _failed_extraction(str(last_error), raw_text, source_channel, prompt_version)


# ── Gemini call ───────────────────────────────────────────────────────────────

async def _call_gemini(raw_text: str, system_prompt: str, api_key: str) -> str:
    payload = {
        "system_instruction": {
            "parts": [{"text": system_prompt}]
        },
        "contents": [
            {
                "role": "user",
                "parts": [{"text": f"Field report:\n\n{raw_text}"}],
            }
        ],
        "generationConfig": {
            "temperature": 0.1,
            "topP": 0.95,
            "maxOutputTokens": 1024,
        },
    }

    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"gemini-2.0-flash:generateContent?key={api_key}"
    )

    async with httpx.AsyncClient(timeout=GEMINI_TIMEOUT_S) as client:
        resp = await client.post(url, json=payload)
        resp.raise_for_status()

    data = resp.json()
    try:
        return data["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError) as e:
        raise ValueError(f"Unexpected Gemini response shape: {data}") from e


# ── Parsing + validation ──────────────────────────────────────────────────────

def _parse_and_validate(
    raw_json: str,
    source_channel: SourceChannel,
    raw_input: str,
    prompt_version: str,
) -> ExtractionResult:
    # Strip accidental markdown fences
    cleaned = re.sub(r"^```(?:json)?\s*", "", raw_json.strip())
    cleaned = re.sub(r"\s*```$", "", cleaned)

    parsed = json.loads(cleaned)  # JSONDecodeError → triggers retry

    # Inject service-level metadata
    parsed["source_channel"] = source_channel.value
    parsed["raw_input"] = raw_input
    parsed["extraction_failed"] = False
    parsed["prompt_version"] = prompt_version

    return ExtractionResult(**parsed)  # ValidationError → triggers retry


def _failed_extraction(
    reason: str,
    raw_input: str,
    source_channel: SourceChannel,
    prompt_version: str,
) -> ExtractionResult:
    """
    Safe fallback when extraction fails twice.
    Stores raw input so NGO can review manually.
    Sets urgency_score=5.0 (medium) so it doesn't get lost in queue.
    """
    return ExtractionResult(
        need_type=NeedType.other,
        description_clean="[Extraction failed — raw input preserved for manual review]",
        urgency_reasoning=f"Automatic extraction failed: {reason}. Defaulting to medium urgency.",
        urgency_score=5.0,
        affected_count=None,
        skills_needed=[],
        location_text="",
        contact_name=None,
        contact_detail=None,
        source_channel=source_channel,
        raw_input=raw_input,
        extraction_failed=True,
        prompt_version=prompt_version,
    )

# ── Groq fallback ─────────────────────────────────────────────────────────────
# Demo-only fallback. Production uses Gemini exclusively.
# Groq provides llama-3.3-70b via OpenAI-compatible API — free tier.

GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL = "llama-3.3-70b-versatile"


async def _try_groq_fallback(
    raw_text: str,
    system_prompt: str,
    source_channel,
    prompt_version: str,
) -> "ExtractionResult | None":
    """
    Try Groq as fallback when Gemini is rate-limited.
    Returns ExtractionResult on success, None if Groq also fails.
    NOTE: Demo environment only — not for production with real beneficiary data.
    """
    from app.core.config import settings
    groq_key = settings.GROQ_API_KEY
    if not groq_key:
        logger.debug("GROQ_API_KEY not set — skipping fallback")
        return None

    logger.info("Gemini rate-limited — attempting Groq fallback (demo mode)")
    try:
        payload = {
            "model": GROQ_MODEL,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Field report:\n\n{raw_text}"},
            ],
            "temperature": 0.1,
            "max_tokens": 1024,
        }
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                GROQ_API_URL,
                json=payload,
                headers={
                    "Authorization": f"Bearer {groq_key}",
                    "Content-Type": "application/json",
                },
            )
            resp.raise_for_status()

        raw_json = resp.json()["choices"][0]["message"]["content"]
        result = _parse_and_validate(raw_json, source_channel, raw_text, prompt_version)
        # Mark that this came from the fallback
        result.urgency_reasoning = f"[Groq fallback — demo mode] {result.urgency_reasoning}"
        logger.info("Groq fallback extraction succeeded")
        return result

    except Exception as e:
        logger.warning(f"Groq fallback also failed: {e}")
        return None