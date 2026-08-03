"""Thin HTTP client wrapper around the 4Geeks LiteLLM gateway.

The academy provides an OpenAI-compatible gateway (https://llm.4geeks.ai)
instead of direct Groq API access, so this module talks to it with plain
httpx requests instead of the Groq SDK, which assumes Groq's own API
paths.
"""

import json

import httpx
from fastapi import HTTPException, status

from src.app.core.config import get_settings

ROUTING_SYSTEM_PROMPT = """You are a strict intent router for a to-do list voice assistant.

You receive a plain-text transcription of something a user said out loud.
Your only job is to translate it into exactly one JSON object describing
which internal API endpoint to call.

The available endpoints are:
- GET /tasks -> list all tasks. No params.
- POST /tasks -> create a task. params: {"title": string, "done": boolean (optional, default false)}
- PUT /tasks/{task_id} -> replace a task entirely. params: {"task_id": integer, "title": string, "done": boolean}
- PATCH /tasks/{task_id} -> partially update a task. params: {"task_id": integer, "title": string (optional), "done": boolean (optional)}
- DELETE /tasks/{task_id} -> delete a task. params: {"task_id": integer}

Respond with ONLY a JSON object, no free text, no markdown, no explanation, in exactly this shape:
{"endpoint": "<path, with {task_id} replaced by the real integer if applicable>", "method": "<GET|POST|PUT|PATCH|DELETE>", "params": {<arguments as described above>}}

Rules:
- "endpoint" must be one of "/tasks" or "/tasks/<id>" with a real integer id.
- "method" must be exactly one of GET, POST, PUT, PATCH, DELETE.
- Never include commentary, apologies, or text outside the JSON object.
- If the instruction refers to a task by number (e.g. "task 2"), use that number as the id.
"""


def _client() -> httpx.Client:
    settings = get_settings()
    return httpx.Client(
        base_url=settings.groq_base_url,
        headers={"Authorization": f"Bearer {settings.groq_api_key}"},
        timeout=settings.request_timeout_seconds,
    )


def route_transcription_to_json(transcription: str) -> dict:
    """Call the LLM gateway to turn a transcription into strict routing JSON."""
    settings = get_settings()
    body = {
        "model": settings.groq_model,
        "messages": [
            {"role": "system", "content": ROUTING_SYSTEM_PROMPT},
            {"role": "user", "content": transcription},
        ],
        "response_format": {"type": "json_object"},
        "temperature": 0,
    }

    try:
        with _client() as client:
            response = client.post("/chat/completions", json=body)
            response.raise_for_status()
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"LLM gateway request failed: {exc}",
        ) from exc

    data = response.json()
    raw_content = data["choices"][0]["message"]["content"] or ""

    try:
        parsed = json.loads(raw_content)
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="The LLM did not return valid JSON for the routing instruction.",
        ) from exc

    if not isinstance(parsed, dict):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="The LLM routing response was not a JSON object.",
        )

    return parsed


def transcribe_audio(file_bytes: bytes, filename: str, language: str | None) -> str:
    """Send recorded audio to the gateway's transcription model and return the text."""
    settings = get_settings()
    data = {"model": settings.groq_transcription_model}
    if language:
        data["language"] = language
    files = {"file": (filename, file_bytes)}

    try:
        with _client() as client:
            response = client.post("/audio/transcriptions", data=data, files=files)
            response.raise_for_status()
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"LLM gateway transcription failed: {exc}",
        ) from exc

    text = (response.json().get("text") or "").strip()
    if not text:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="The transcription service returned an empty result.",
        )
    return text