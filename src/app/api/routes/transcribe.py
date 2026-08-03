from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status
from groq import APIConnectionError, APIStatusError, RateLimitError

from src.app.api.routes.instruction import build_instruction_from_transcription, get_groq_client
from src.app.api.routes.tasks import execute_task_instruction
from src.app.core.config import get_settings
from src.app.schemas.voice import TranscribeFlowResponse
from src.app.utils.language import normalize_transcription_language

router = APIRouter(tags=["transcribe"])


@router.get("/")
async def healthcheck() -> dict[str, str]:
    return {"status": "ok"}


@router.post("/transcribe", response_model=TranscribeFlowResponse)
async def transcribe_and_run_flow(
    file: UploadFile = File(...),
    language: str | None = Form(default=None),
) -> TranscribeFlowResponse:
    try:
        normalized_language = normalize_transcription_language(language)
        transcription = await transcribe_audio(file=file, language=normalized_language)
        instruction = build_instruction_from_transcription(transcription)
        result = execute_task_instruction(instruction)

        return TranscribeFlowResponse(
            transcription=transcription,
            instruction=instruction,
            result=result,
        )
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


async def transcribe_audio(file: UploadFile, language: str | None) -> str:
    if file.content_type and not file.content_type.startswith("audio/"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The uploaded file must be an audio file.",
        )

    audio_bytes = await file.read()
    if not audio_bytes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The uploaded audio file is empty.",
        )

    settings = get_settings()
    client = get_groq_client()
    payload: dict[str, Any] = {
        "file": (file.filename or "command.webm", audio_bytes),
        "model": settings.groq_transcription_model,
        "temperature": 0,
    }

    if language:
        payload["language"] = language

    transcription = client.audio.transcriptions.create(**payload)
    transcription_text = extract_transcription_text(transcription)

    if not transcription_text:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Groq returned an empty transcription payload",
        )

    return transcription_text


def extract_transcription_text(raw_response: Any) -> str:
    if isinstance(raw_response, str):
        return raw_response.strip()

    text_attr = getattr(raw_response, "text", None)
    if isinstance(text_attr, str):
        return text_attr.strip()

    if hasattr(raw_response, "model_dump"):
        data = raw_response.model_dump()
        value = data.get("text")
        if isinstance(value, str):
            return value.strip()

    if isinstance(raw_response, dict):
        value = raw_response.get("text")
        if isinstance(value, str):
            return value.strip()

    return ""
