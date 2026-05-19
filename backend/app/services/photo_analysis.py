"""Photo analysis via GPT-4o-mini vision (optional).

When listing photos are available AND OPENAI_API_KEY is set, sends the
first few photos to extract renovation state, view quality, and natural
light assessment. Skips silently when unavailable.
"""
from __future__ import annotations

import json
import logging
from typing import Literal

import httpx

from ..config import settings
from ..models.schemas import PhotoAnalysis

log = logging.getLogger(__name__)

_SYSTEM_PROMPT = """\
You are a Paris real estate photo analyst. Given apartment listing photos,
assess the following three attributes. Respond ONLY with a JSON object:

{
  "renovation_state": "raw" | "dated" | "recent" | "premium",
  "view_quality": "courtyard" | "street" | "panoramic" | "landmark" | "unknown",
  "natural_light": "dark" | "average" | "bright"
}

Definitions:
- renovation_state: "raw" = stripped/unfinished, "dated" = livable but old
  finishes (pre-2000), "recent" = renovated in last 10 years, "premium" =
  high-end materials/designer finish.
- view_quality: "landmark" if Eiffel Tower, Sacré-Coeur, Notre-Dame or similar
  monument is clearly visible from windows; "panoramic" = wide open skyline;
  "street" = typical street view; "courtyard" = inner courtyard; "unknown"
  if windows/views not shown.
- natural_light: based on visible light in rooms; "dark" = few/small windows
  or north-facing, "bright" = abundant natural light flooding in.
"""


async def analyze_photos(
    photo_urls: list[str],
    *,
    max_photos: int = 3,
) -> PhotoAnalysis | None:
    """Analyze listing photos with vision LLM. Returns None if unavailable."""
    cfg = settings()
    if not cfg.openai_api_key:
        return None
    if not photo_urls:
        return None

    urls_to_send = photo_urls[:max_photos]
    content: list[dict] = [{"type": "text", "text": "Analyze these apartment listing photos:"}]
    for url in urls_to_send:
        content.append({
            "type": "image_url",
            "image_url": {"url": url, "detail": "low"},
        })

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {cfg.openai_api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "gpt-4o-mini",
                    "messages": [
                        {"role": "system", "content": _SYSTEM_PROMPT},
                        {"role": "user", "content": content},
                    ],
                    "max_tokens": 150,
                    "temperature": 0.2,
                },
            )
            if resp.status_code != 200:
                log.warning("photo_analysis_api_error status=%d", resp.status_code)
                return None
            data = resp.json()
    except Exception as e:
        log.warning("photo_analysis_request_failed err=%s", str(e)[:200])
        return None

    try:
        raw_text = data["choices"][0]["message"]["content"]
        cleaned = raw_text.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("\n", 1)[1].rsplit("```", 1)[0].strip()
        parsed = json.loads(cleaned)
        return PhotoAnalysis(
            renovation_state=_validate_enum(
                parsed.get("renovation_state"), ["raw", "dated", "recent", "premium"], "recent"
            ),
            view_quality=_validate_enum(
                parsed.get("view_quality"),
                ["courtyard", "street", "panoramic", "landmark", "unknown"],
                "unknown",
            ),
            natural_light=_validate_enum(
                parsed.get("natural_light"), ["dark", "average", "bright"], "average"
            ),
        )
    except (KeyError, json.JSONDecodeError, ValueError) as e:
        log.warning("photo_analysis_parse_failed err=%s", str(e)[:200])
        return None


def _validate_enum(value: str | None, allowed: list[str], default: str) -> str:
    if value and value.lower() in allowed:
        return value.lower()
    return default
