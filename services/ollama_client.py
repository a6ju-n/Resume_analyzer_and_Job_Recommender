"""
Ollama HTTP client for the AI resume analysis (quality score and advice).

Job matching does not use the AI: see services/job_matcher.py.

All calls go to the local Ollama REST API (default: http://localhost:11434).
The model and timeout are read from Flask's current_app.config so they are
configurable via environment variables without code changes.

Design rules
------------
- Never invent candidate qualifications — only analyse what's extracted.
- Return structured JSON validated against expected keys.
- Degrade gracefully: if Ollama is offline, return an error dict instead of
  raising so the route can store the resume and show a friendly message.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any

import requests
from flask import current_app

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Sentinel returned when Ollama is unavailable or returns bad JSON
# ---------------------------------------------------------------------------
_ANALYSIS_ERROR: dict[str, Any] = {
    "error": True,
    "message": "",
    "quality_score": None,
    "strengths": [],
    "weaknesses": [],
    "missing_information": [],
    "improvement_suggestions": [],
    "overall_summary": "",
}

# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------

def is_ollama_available() -> bool:
    """Return True if the local Ollama server is reachable."""
    host = current_app.config["OLLAMA_HOST"]
    try:
        r = requests.get(f"{host}/api/tags", timeout=5)
        return r.status_code == 200
    except Exception:
        return False


def get_model() -> str:
    """The model chosen on the Settings page, else the OLLAMA_MODEL default."""
    from database.models import AppSetting
    return AppSetting.get("ollama_model") or current_app.config["OLLAMA_MODEL"]


def list_models() -> list[str]:
    """Names of the models installed in Ollama ([] if it is not reachable)."""
    host = current_app.config["OLLAMA_HOST"]
    try:
        r = requests.get(f"{host}/api/tags", timeout=5)
        r.raise_for_status()
        return sorted(m["name"] for m in r.json().get("models", []) if m.get("name"))
    except Exception:
        return []


def analyse_resume(parsed_data: dict, raw_text: str) -> dict[str, Any]:
    """
    Send the extracted resume to Ollama and return a validated analysis dict.

    Keys in the returned dict
    -------------------------
    error                  bool
    quality_score          int  0-100  (null if unavailable)
    strengths              list[str]
    weaknesses             list[str]
    missing_information    list[str]
    improvement_suggestions list[str]
    overall_summary        str
    """
    prompt = _build_analysis_prompt(parsed_data, raw_text)
    raw = _call_ollama(prompt)
    if raw is None:
        result = dict(_ANALYSIS_ERROR)
        result["message"] = "Ollama is not available. Start Ollama and re-analyse."
        return result

    parsed = _parse_json_from_response(raw)
    if parsed is None:
        result = dict(_ANALYSIS_ERROR)
        result["message"] = "Ollama returned an unexpected response format."
        result["raw_response"] = raw[:500]
        return result

    return _validate_analysis(parsed)


# ---------------------------------------------------------------------------
# Prompt builders
# ---------------------------------------------------------------------------

def _build_analysis_prompt(parsed_data: dict, raw_text: str) -> str:
    # Summarise parsed data to keep the prompt short
    skills_str  = ", ".join(parsed_data.get("skills", [])[:20]) or "none detected"
    langs_str   = ", ".join(parsed_data.get("programming_languages", [])) or "none detected"
    fw_str      = ", ".join(parsed_data.get("frameworks", [])) or "none detected"
    exp_snippet = (parsed_data.get("experience") or "")[:400]
    proj_snippet = (parsed_data.get("projects") or "")[:400]
    edu_snippet  = (parsed_data.get("education") or "")[:300]

    return f"""You are a senior technical recruiter reviewing a candidate's resume.
Analyse ONLY the information provided. Do not invent experience, skills, or achievements.

CANDIDATE SUMMARY:
- Skills: {skills_str}
- Programming languages: {langs_str}
- Frameworks/tools: {fw_str}
- Education (excerpt): {edu_snippet}
- Experience (excerpt): {exp_snippet}
- Projects (excerpt): {proj_snippet}

TASK: Provide a JSON object (no markdown, no code fences, pure JSON) with EXACTLY these keys:
{{
  "quality_score": <integer 0-100 representing overall resume quality>,
  "strengths": [<list of 2-5 specific strength strings>],
  "weaknesses": [<list of 2-5 specific weakness strings>],
  "missing_information": [<list of items missing from the resume, e.g. "GitHub link", "quantified impact">],
  "improvement_suggestions": [<list of 3-6 actionable improvement strings>],
  "overall_summary": "<2-3 sentence summary of the resume>"
}}

Base the quality_score on: completeness, clarity, technical depth, project descriptions, and
quantified achievements. Only analyse what is present — do not assume anything not stated.
Output ONLY the JSON object, nothing else."""


# ---------------------------------------------------------------------------
# HTTP call
# ---------------------------------------------------------------------------

def _call_ollama(prompt: str) -> str | None:
    host    = current_app.config["OLLAMA_HOST"]
    model   = get_model()
    timeout = current_app.config["OLLAMA_TIMEOUT"]

    payload = {
        "model":  model,
        "prompt": prompt,
        "stream": False,
        "format": "json",
        "options": {
            "temperature": 0.1,     # low temp for deterministic structured output
            "num_predict": 1024,
        },
    }
    try:
        resp = requests.post(
            f"{host}/api/generate",
            json=payload,
            timeout=timeout,
        )
        resp.raise_for_status()
        data = resp.json()
        return data.get("response", "")
    except requests.exceptions.ConnectionError:
        log.warning("Ollama connection refused at %s", host)
        return None
    except requests.exceptions.Timeout:
        log.warning("Ollama timed out after %s s", timeout)
        return None
    except Exception as exc:
        log.error("Ollama error: %s", exc)
        return None


# ---------------------------------------------------------------------------
# JSON extraction + validation
# ---------------------------------------------------------------------------

def _parse_json_from_response(text: str) -> Any:
    """
    Extract JSON from an Ollama response that may contain surrounding prose,
    <think> tags (for thinking models like qwen3), or code fences.
    """
    if not text:
        return None

    # Strip <think>…</think> blocks emitted by qwen3 reasoning mode
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()

    # Try direct parse first
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Strip markdown code fences if present
    fence_match = re.search(r"```(?:json)?\s*([\s\S]+?)```", text)
    if fence_match:
        try:
            return json.loads(fence_match.group(1).strip())
        except json.JSONDecodeError:
            pass

    # Find first { or [ and try from there
    for start_char, end_char in [("{", "}"), ("[", "]")]:
        idx = text.find(start_char)
        if idx != -1:
            # Find the matching closing bracket
            snippet = text[idx:]
            last = snippet.rfind(end_char)
            if last != -1:
                try:
                    return json.loads(snippet[: last + 1])
                except json.JSONDecodeError:
                    pass

    log.warning("Could not parse JSON from Ollama response: %.200s", text)
    return None


def _validate_analysis(d: dict) -> dict[str, Any]:
    """Ensure all required keys exist with the correct types."""
    result: dict[str, Any] = {"error": False, "message": ""}
    result["quality_score"] = _coerce_int(d.get("quality_score"), 0, 100)
    result["strengths"]     = _coerce_str_list(d.get("strengths"))
    result["weaknesses"]    = _coerce_str_list(d.get("weaknesses"))
    result["missing_information"]     = _coerce_str_list(d.get("missing_information"))
    result["improvement_suggestions"] = _coerce_str_list(d.get("improvement_suggestions"))
    result["overall_summary"] = str(d.get("overall_summary") or "")
    return result


# ---------------------------------------------------------------------------
# Type coercions
# ---------------------------------------------------------------------------

def _coerce_int(value: Any, lo: int, hi: int) -> int | None:
    try:
        v = int(value)
        return max(lo, min(hi, v))
    except (TypeError, ValueError):
        return None


def _coerce_str_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(i) for i in value if i]
    if isinstance(value, str) and value.strip():
        return [value]
    return []
