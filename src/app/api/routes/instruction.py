import json

from fastapi import APIRouter, HTTPException, status
from groq import APIConnectionError, APIStatusError, Groq, RateLimitError
from pydantic import ValidationError

from src.app.core.config import get_settings
from src.app.schemas.voice import InstructionPayload, InstructionRequest

router = APIRouter(tags=["instruction"])

SYSTEM_PROMPT = """
You are an API instruction planner.
Given a natural-language transcription from a user, decide which backend endpoint to call.
You must return only valid JSON with this exact shape:
{
  "endpoint": "string",
  "method": "GET|POST|PUT|PATCH|DELETE",
  "params": {}
}

Rules:
- Return JSON only. No markdown, no explanations, no extra keys.
- endpoint must start with "/".
- method must be uppercase.
- params must always be an object (use {} when no params are needed).
- Prefer /tasks for task management intents.
""".strip()


def get_groq_client() -> Groq:
    settings = get_settings()
    return Groq(api_key=settings.groq_api_key)


def build_instruction_from_transcription(transcription: str) -> InstructionPayload:
    settings = get_settings()
    client = get_groq_client()

    completion = client.chat.completions.create(
        model=settings.groq_model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": transcription},
        ],
        temperature=0,
        response_format={"type": "json_object"},
    )

    content = completion.choices[0].message.content
    if not content:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Groq returned an empty instruction payload",
        )

    try:
        return InstructionPayload.model_validate(json.loads(content))
    except (json.JSONDecodeError, ValidationError) as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Groq returned an invalid instruction JSON payload",
        ) from exc


@router.post("/instruction", response_model=InstructionPayload)
def route_instruction(
    payload: InstructionRequest,
) -> InstructionPayload:
    try:
        return build_instruction_from_transcription(payload.transcription)
    except RateLimitError as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Groq rate limit exceeded",
        ) from exc
    except APIConnectionError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Failed to connect to Groq API",
        ) from exc
    except APIStatusError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Groq API error: {exc.status_code}",
        ) from exc
