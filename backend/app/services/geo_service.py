"""
geo_service.py — Location text → lat/lng using Nominatim (OpenStreetMap)

Why Nominatim:
- Completely free, no API key needed
- Good coverage of Indian cities, districts, landmarks
- Rate limit: 1 request/second (more than enough for intake pipeline)
- Handles: "near Shivaji Chowk, Ward 7", "behind Sai Mandir, Pune",
           "Sylhet district", "MG Road area, Bengaluru" etc.

Returns: (lat, lng, confidence)
  confidence 0.0 = failed / no result
  confidence 0.4 = city/district level match
  confidence 0.7 = neighbourhood/area level match
  confidence 0.9 = street/landmark level match
"""

import logging
from typing import Optional
import httpx

logger = logging.getLogger(__name__)

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
HEADERS = {
    # Nominatim requires a descriptive User-Agent
    "User-Agent": "SETU-DisasterRelief/1.0 (disaster coordination platform; contact@setu-app.org)"
}

# Confidence mapping based on Nominatim OSM type / class
_HIGH_CONFIDENCE = {"amenity", "building", "highway", "place", "tourism", "historic"}
_MED_CONFIDENCE = {"suburb", "neighbourhood", "quarter"}
_LOW_CONFIDENCE = {"city", "town", "village", "district", "county", "state"}


async def geocode(location_text: str, country_hint: str = "India") -> tuple[float, float, float]:
    """
    Convert a raw location string to (lat, lng, confidence).
    Falls back gracefully — never raises, always returns a tuple.

    Args:
        location_text: Raw location as extracted from the report
                       e.g. "near Shivaji Chowk, Ward 7"
        country_hint:  Bias results toward this country

    Returns:
        (lat, lng, confidence) where confidence is 0.0 if geocoding failed
    """
    if not location_text or len(location_text.strip()) < 3:
        return 0.0, 0.0, 0.0

    # Clean up common noise from extraction
    cleaned = _clean_location(location_text)
    if not cleaned:
        return 0.0, 0.0, 0.0

    # Try progressively broader queries if specific one fails
    queries = _build_query_variants(cleaned, country_hint)

    for query, expected_confidence in queries:
        result = await _nominatim_query(query)
        if result:
            lat, lng, osm_type, osm_class = result
            confidence = _calc_confidence(osm_type, osm_class, expected_confidence)
            logger.info(f"Geocoded '{location_text}' → ({lat:.4f}, {lng:.4f}) conf={confidence:.2f} via '{query}'")
            return lat, lng, confidence

    logger.warning(f"Geocoding failed for: '{location_text}'")
    return 0.0, 0.0, 0.0


async def _nominatim_query(query: str) -> Optional[tuple[float, float, str, str]]:
    """Hit Nominatim and return (lat, lng, type, class) for the top result."""
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.get(
                NOMINATIM_URL,
                params={
                    "q": query,
                    "format": "json",
                    "limit": 1,
                    "addressdetails": 1,
                    "countrycodes": "in",   # bias toward India
                },
                headers=HEADERS,
            )
            resp.raise_for_status()
            results = resp.json()

        if not results:
            return None

        top = results[0]
        return (
            float(top["lat"]),
            float(top["lon"]),
            top.get("type", ""),
            top.get("class", ""),
        )
    except Exception as e:
        logger.debug(f"Nominatim query failed for '{query}': {e}")
        return None


def _build_query_variants(location: str, country: str) -> list[tuple[str, float]]:
    """
    Build a list of (query_string, max_confidence) pairs to try in order.
    Specific → broad. Each step drops a word or adds a broader context.
    """
    variants = []

    # 1. Exact as extracted + country
    variants.append((f"{location}, {country}", 0.9))

    # 2. Strip common noise words
    simplified = _strip_noise(location)
    if simplified != location:
        variants.append((f"{simplified}, {country}", 0.8))

    # 3. Take only the last comma-separated segment (usually the area name)
    parts = [p.strip() for p in location.split(",") if p.strip()]
    if len(parts) > 1:
        variants.append((f"{parts[-1]}, {country}", 0.6))
        # Also try second-to-last + last
        variants.append((f"{parts[-2]}, {parts[-1]}, {country}", 0.7))

    # 4. First meaningful word cluster (landmark name)
    if parts:
        variants.append((f"{parts[0]}, {country}", 0.5))

    return variants


def _clean_location(text: str) -> str:
    """Remove extraction artifacts and normalise."""
    import re
    # Remove common extraction noise
    noise_patterns = [
        r"(?i)near\s+",
        r"(?i)behind\s+",
        r"(?i)opposite\s+",
        r"(?i)next\s+to\s+",
        r"(?i)ward\s+\d+",
        r"(?i)sector\s+\d+",
        r"(?i)\bi\s+think\b.*",
        r"(?i)\bmaybe\b.*",
        r"(?i)\bidk\b.*",
        r"(?i)\bsomewhere\b.*",
    ]
    cleaned = text.strip()
    for pattern in noise_patterns:
        cleaned = re.sub(pattern, "", cleaned).strip()
    # Collapse multiple spaces/commas
    cleaned = re.sub(r"\s+", " ", cleaned)
    cleaned = re.sub(r",\s*,", ",", cleaned)
    return cleaned.strip(" ,")


def _strip_noise(text: str) -> str:
    """Strip directional/relational prefixes."""
    import re
    return re.sub(r"(?i)^(near|behind|opposite|next to|in front of)\s+", "", text).strip()


def _calc_confidence(osm_type: str, osm_class: str, max_confidence: float) -> float:
    """Map OSM result type to a confidence score."""
    combined = f"{osm_class}/{osm_type}".lower()

    if any(t in combined for t in ["amenity", "building", "highway", "tourism", "historic", "shop"]):
        return min(max_confidence, 0.9)
    if any(t in combined for t in ["suburb", "neighbourhood", "quarter", "residential"]):
        return min(max_confidence, 0.75)
    if any(t in combined for t in ["city", "town", "village"]):
        return min(max_confidence, 0.5)
    if any(t in combined for t in ["district", "county", "state"]):
        return min(max_confidence, 0.35)

    return min(max_confidence, 0.4)