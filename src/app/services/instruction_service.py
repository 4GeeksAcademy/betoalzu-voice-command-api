"""Business logic for turning a transcription into a routing decision."""

from fastapi import HTTPException, status
from pydantic import ValidationError

from src.app.schemas.voice import InstructionPayload
from src.app.services.groq_client import route_transcription_to_json


def build_instruction(transcription: str) -> InstructionPayload:
    routing = route_transcription_to_json(transcription)
    try:
        return InstructionPayload(
            endpoint=routing.get("endpoint", ""),
            method=routing.get("method", ""),
            params=routing.get("params", {}) or {},
        )
    except ValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Groq routing response did not match the expected shape: {exc}",
        ) from exc