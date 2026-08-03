from fastapi import APIRouter, HTTPException, Request, status

from src.app.schemas.voice import TranscribeFlowResponse
from src.app.services.groq_client import transcribe_audio
from src.app.services.instruction_service import build_instruction
from src.app.services.task_executor import execute_instruction
from src.app.utils.language import normalize_transcription_language

router = APIRouter(tags=["transcribe"])


@router.get("/")
async def healthcheck() -> dict[str, str]:
    return {"status": "ok"}


@router.post("/transcribe", response_model=TranscribeFlowResponse)
async def transcribe_and_run_flow(request: Request) -> TranscribeFlowResponse:
    content_type = request.headers.get("content-type", "")

    if content_type.startswith("multipart/form-data"):
        form = await request.form()
        upload = form.get("file")
        if upload is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Missing 'file' field in the multipart request.",
            )
        language = normalize_transcription_language(form.get("language"))
        audio_bytes = await upload.read()
        transcription = transcribe_audio(
            file_bytes=audio_bytes,
            filename=upload.filename or "audio.webm",
            language=language,
        )
    elif content_type.startswith("application/json"):
        body = await request.json()
        transcription = (body.get("transcription") or "").strip()
        if not transcription:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Missing 'transcription' field in the JSON body.",
            )
    else:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Expected multipart/form-data audio or application/json transcription.",
        )

    instruction = build_instruction(transcription)
    result = execute_instruction(instruction)

    return TranscribeFlowResponse(
        transcription=transcription,
        instruction=instruction,
        result=result,
    )