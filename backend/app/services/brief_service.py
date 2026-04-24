"""
Brief generation service.

Generates a WhatsApp-sendable volunteer mission brief from a NeedCard
+ matched volunteer's skills, using Gemini 1.5 Pro with a grounded prompt.

Design decisions:
  - Prompt loaded from prompts/brief_v1.txt (version-controlled)
  - NeedCard fields are serialized to a compact JSON string — not the full
    model dump, only fields relevant to a brief (no embeddings, hashes, etc.)
  - Language is driven by volunteer.language_pref (ISO 639-1)
  - Single retry on timeout; returns a safe fallback brief on both failures
  - Brief stored in DispatchRecord.brief_text (draft state until NGO approves)
"""

import json
import logging
import os
import re
from pathlib import Path

import httpx

logger = logging.getLogger(__name__)

PROMPTS_DIR = Path(__file__).parent.parent / "prompts"
GEMINI_TIMEOUT_S = 15.0
BRIEF_RETRIES = 1

# Word count targets
BRIEF_MIN_WORDS = 60
BRIEF_MAX_WORDS = 140  # soft ceiling; warn but don't fail

# Supported languages (ISO 639-1 → display name for prompt)
SUPPORTED_LANGUAGES = {
    "en": "English",
    "hi": "Hindi",
    "bn": "Bengali",
    "mr": "Marathi",
    "te": "Telugu",
    "ta": "Tamil",
    "or": "Odia",
}


class BriefResult:
    def __init__(
        self,
        brief_text: str,
        language: str,
        word_count: int,
        generation_failed: bool = False,
        prompt_version: str = "v1",
    ):
        self.brief_text = brief_text
        self.language = language
        self.word_count = word_count
        self.generation_failed = generation_failed
        self.prompt_version = prompt_version

    def dict(self):
        return {
            "brief_text": self.brief_text,
            "language": self.language,
            "word_count": self.word_count,
            "generation_failed": self.generation_failed,
            "prompt_version": self.prompt_version,
        }


async def generate_brief(
    needcard_dict: dict,
    volunteer_skills: list[str],
    language_pref: str = "en",
    prompt_version: str = "v1",
) -> BriefResult:
    """
    Generate a mission brief for a volunteer.

    Args:
        needcard_dict:     NeedCard.to_brief_context() — compact field subset
        volunteer_skills:  list of canonical skill strings
        language_pref:     ISO 639-1 code (default "en")
        prompt_version:    prompt file to use (default "v1")

    Returns BriefResult. Never raises — returns generation_failed=True on error.
    """
    from app.core.config import settings
    api_key = settings.GEMINI_API_KEY
    if not api_key:
        return _fallback_brief(language_pref, "GEMINI_API_KEY not set")

    language = SUPPORTED_LANGUAGES.get(language_pref, "English")

    try:
        prompt_template = _load_prompt(prompt_version)
    except FileNotFoundError as e:
        return _fallback_brief(language_pref, str(e))

    needcard_json = _serialize_needcard(needcard_dict)
    skills_str = ", ".join(volunteer_skills) if volunteer_skills else "general volunteering"

    prompt = prompt_template.format(
        language=language,
        needcard_json=needcard_json,
        volunteer_skills=skills_str,
    )

    last_error = None
    for attempt in range(BRIEF_RETRIES + 1):
        try:
            raw = await _call_gemini(prompt, api_key)
            return _process_response(raw, language_pref, prompt_version)
        except (httpx.TimeoutException, httpx.HTTPStatusError) as e:
            last_error = e
            logger.warning(f"Brief generation attempt {attempt + 1} failed: {e}")
        except Exception as e:
            last_error = e
            logger.warning(f"Brief generation attempt {attempt + 1} unexpected error: {e}")

    logger.error(f"Brief generation failed after {BRIEF_RETRIES + 1} attempts: {last_error}")
    return _fallback_brief(language_pref, str(last_error))


def _serialize_needcard(needcard_dict: dict) -> str:
    """
    Serialize only the fields relevant to brief generation.
    Strips embeddings, hashes, schema metadata — keeps it compact.
    """
    relevant_fields = [
        "need_type", "description_clean", "urgency_score_eff",
        "urgency_reasoning", "affected_count", "skills_needed",
        "location_text_raw", "contact_name", "contact_detail",
        "geo_confidence",
    ]
    compact = {k: needcard_dict[k] for k in relevant_fields if k in needcard_dict}

    # Add human-readable urgency label
    score = compact.get("urgency_score_eff", 5.0)
    if score >= 9:
        compact["urgency_label"] = "CRITICAL"
    elif score >= 7:
        compact["urgency_label"] = "HIGH"
    elif score >= 5:
        compact["urgency_label"] = "MODERATE"
    elif score >= 3:
        compact["urgency_label"] = "LOW"
    else:
        compact["urgency_label"] = "ROUTINE"

    return json.dumps(compact, ensure_ascii=False, indent=2)


async def _call_gemini(prompt: str, api_key: str) -> str:
    payload = {
        "contents": [
            {"role": "user", "parts": [{"text": prompt}]}
        ],
        "generationConfig": {
            "temperature": 0.3,    # slight warmth for natural phrasing, low enough to stay grounded
            "topP": 0.9,
            "maxOutputTokens": 512,
            # No JSON mode — we want plain text
        },
    }

    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"gemini-1.5-pro:generateContent?key={api_key}"
    )

    async with httpx.AsyncClient(timeout=GEMINI_TIMEOUT_S) as client:
        resp = await client.post(url, json=payload)
        resp.raise_for_status()

    data = resp.json()
    try:
        return data["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError) as e:
        raise ValueError(f"Unexpected Gemini response: {data}") from e


def _process_response(raw: str, language_pref: str, prompt_version: str) -> BriefResult:
    brief = raw.strip()

    # Strip any accidental markdown
    brief = re.sub(r"^```.*?\n", "", brief, flags=re.DOTALL)
    brief = re.sub(r"\n```$", "", brief).strip()

    word_count = len(brief.split())

    if word_count < BRIEF_MIN_WORDS:
        logger.warning(f"Brief too short: {word_count} words (min {BRIEF_MIN_WORDS})")
    if word_count > BRIEF_MAX_WORDS:
        logger.warning(f"Brief too long: {word_count} words (max {BRIEF_MAX_WORDS})")

    return BriefResult(
        brief_text=brief,
        language=language_pref,
        word_count=word_count,
        generation_failed=False,
        prompt_version=prompt_version,
    )


def _load_prompt(version: str) -> str:
    path = PROMPTS_DIR / f"brief_{version}.txt"
    if not path.exists():
        raise FileNotFoundError(f"Brief prompt not found: {path}")
    return path.read_text(encoding="utf-8")


def _fallback_brief(language_pref: str, reason: str) -> BriefResult:
    """
    Safe fallback when generation fails.
    NGO will see generation_failed=True and can write the brief manually.
    """
    logger.error(f"Brief generation fallback triggered: {reason}")
    text = (
        "[Brief generation failed — please write this brief manually before dispatching. "
        f"Error: {reason[:100]}]"
    )
    return BriefResult(
        brief_text=text,
        language=language_pref,
        word_count=len(text.split()),
        generation_failed=True,
        prompt_version="fallback",
    )