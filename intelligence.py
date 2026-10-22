from __future__ import annotations

import json
import re
from typing import Any

import httpx

from ..config import LENGTH_SECONDS, settings


class LLMError(RuntimeError):
    pass


def _endpoint() -> tuple[str, str, str]:
    if settings.manus_api_url and settings.manus_api_key:
        return settings.manus_api_url, settings.manus_api_key, settings.llm_model
    if settings.openai_api_key:
        return settings.openai_api_base, settings.openai_api_key, settings.llm_model
    raise LLMError("No LLM credentials are configured. Set MANUS_API_URL and MANUS_API_KEY or OPENAI_API_KEY.")


def completion(system: str, user: str) -> str:
    base, key, model = _endpoint()
    body: dict[str, Any] = {"messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
    if model:
        body["model"] = model
    try:
        with httpx.Client(timeout=240) as client:
            response = client.post(f"{base}/v1/chat/completions", headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"}, json=body)
            response.raise_for_status()
            payload = response.json()
    except httpx.HTTPError as exc:
        raise LLMError(f"LLM request failed: {exc}") from exc
    if payload.get("error"):
        raise LLMError(str(payload["error"].get("message") or payload["error"]))
    content = (((payload.get("choices") or [{}])[0]).get("message") or {}).get("content")
    if not content:
        raise LLMError("The LLM returned no completion content.")
    return str(content).strip()


def parse_json_object(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", cleaned, flags=re.IGNORECASE | re.MULTILINE).strip()
    try:
        value = json.loads(cleaned)
    except json.JSONDecodeError:
        start, end = cleaned.find("{"), cleaned.rfind("}")
        if start < 0 or end <= start:
            return {"raw": text}
        try:
            value = json.loads(cleaned[start : end + 1])
        except json.JSONDecodeError:
            return {"raw": text}
    return value if isinstance(value, dict) else {"raw": text}


def analyze_content(transcript: str, scenes: list[dict], spoiler: bool) -> dict[str, Any]:
    prompt = f"""Analyze this movie transcript and scene list for a transformative recap. Return JSON with keys characters, plot_points, key_scenes, climax, ending, themes, and insights. Each key_scenes item must include scene_index, reason, and a short Burmese or English selection note. Do not reproduce dialogue verbatim. Spoilers allowed: {spoiler}.\n\nSCENES:\n{json.dumps(scenes[:120], ensure_ascii=False)}\n\nTRANSCRIPT:\n{transcript[:50000]}"""
    result = parse_json_object(completion(
        "You are a careful film editor and story analyst. Never claim to have seen material not present in the supplied transcript or scene list.",
        prompt,
    ))
    result["spoiler"] = spoiler
    return result


def _contains_myanmar(text: str) -> bool:
    return any("\u1000" <= char <= "\u109f" for char in text)


def write_burmese_script(analysis: dict[str, Any], transcript: str, length: str, tone: str, spoiler: bool) -> dict[str, Any]:
    low, high = LENGTH_SECONDS[length]
    prompt = f"""Write a completely original Burmese Unicode movie recap script for spoken narration. Target duration is {low}-{high} seconds. Tone: {tone}. Spoilers: {spoiler}. Structure exactly as hook, intro, plot, key scenes, climax, ending, and personal commentary/opinion. Paraphrase everything; do not copy dialogue. Include the narrator's own insights about why selected scenes work. Return JSON with keys title, script, sections (array of {{name,text}}), and estimated_seconds. The script must be Burmese Unicode, not transliteration.\n\nANALYSIS:\n{json.dumps(analysis, ensure_ascii=False)}\n\nTRANSCRIPT CONTEXT:\n{transcript[:20000]}"""
    result = parse_json_object(completion(
        "You are a Burmese-language film recap writer. Write natural spoken Myanmar Unicode with clear pacing and no invented facts.",
        prompt,
    ))
    script = str(result.get("script") or "")
    if not _contains_myanmar(script):
        raise LLMError("The LLM response did not contain Burmese Unicode script text.")
    result["script"] = script
    result["estimated_seconds"] = float(result.get("estimated_seconds") or max(low, min(high, len(script) / 5.5)))
    return result


def generate_metadata(script: str, analysis: dict[str, Any]) -> dict[str, Any]:
    result = parse_json_object(completion(
        "You create accurate Burmese social metadata for a transformative movie recap. Keep claims grounded in the supplied script.",
        f"Return JSON with title, description, tags (array), and thumbnail_suggestion. Script:\n{script[:16000]}\nAnalysis:\n{json.dumps(analysis, ensure_ascii=False)[:12000]}",
    ))
    return result
