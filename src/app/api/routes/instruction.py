import json
import re
from typing import Any

from fastapi import APIRouter, HTTPException, status
from groq import APIConnectionError, APIStatusError, Groq, RateLimitError
from pydantic import ValidationError

from src.app.core.config import get_settings
from src.app.schemas.voice import (
    InstructionPayload,
    InstructionRequest,
    TaskCreate,
    TaskReplace,
    TaskUpdate,
)

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
- All routing decisions must come from your semantic understanding of the transcription.
- Do not assume or mention any hardcoded keyword heuristics from server code.

Supported task API contract:
- GET /tasks -> params must be {}
- POST /tasks -> params must include: {"title": string}. Optional: {"done": boolean}
- PUT /tasks/{task_id} -> params must include both: {"title": string, "done": boolean}
- PATCH /tasks/{task_id} -> params can include one or both: {"title": string, "done": boolean}
- DELETE /tasks/{task_id} -> params must be {}

Important:
- When user intent is "create/add a task", return endpoint "/tasks", method "POST", and include non-empty "title".
- When user references a specific id, use endpoint "/tasks/{id}" with that numeric id.
""".strip()

REPAIR_PROMPT = """
You are fixing an invalid API routing payload.
Return only valid JSON with this shape:
{
    "endpoint": "string",
    "method": "GET|POST|PUT|PATCH|DELETE",
    "params": {}
}

Task API contract:
- GET /tasks -> params must be {}
- POST /tasks -> params must include non-empty "title" string. Optional: "done" boolean
- PUT /tasks/{task_id} -> params must include both "title" string and "done" boolean
- PATCH /tasks/{task_id} -> params can include "title" and/or "done"
- DELETE /tasks/{task_id} -> params must be {}

Rules:
- Return JSON only. No markdown or extra keys.
- Use the original transcription meaning to decide values.
- If user intent is to create/add a task, method must be POST and params must include non-empty title.
""".strip()

TASK_ITEM_ENDPOINT = re.compile(r"^/tasks/(?P<task_id>\d+)/?$")


def get_groq_client() -> Groq:
    settings = get_settings()
    return Groq(api_key=settings.groq_api_key)


def build_instruction_from_transcription(transcription: str) -> InstructionPayload:
    settings = get_settings()
    client = get_groq_client()

    instruction = request_instruction_payload(
        client=client,
        model=settings.groq_model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": transcription},
        ],
    )

    try:
        validate_instruction_contract(instruction)
        return instruction
    except HTTPException as exc:
        # One semantic repair pass avoids transient invalid payloads like POST /tasks with {} params.
        repaired = request_instruction_payload(
            client=client,
            model=settings.groq_model,
            messages=[
                {"role": "system", "content": REPAIR_PROMPT},
                {
                    "role": "user",
                    "content": (
                        f"Original transcription:\n{transcription}\n\n"
                        f"Invalid payload:\n{instruction.model_dump_json(indent=2)}\n\n"
                        f"Validation error:\n{exc.detail}\n\n"
                        "Return a corrected JSON payload now."
                    ),
                },
            ],
        )
        validate_instruction_contract(repaired)
        return repaired


def request_instruction_payload(
    client: Groq,
    model: str,
    messages: list[dict[str, str]],
) -> InstructionPayload:
    completion = client.chat.completions.create(
        model=model,
        messages=messages,
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
        raw: Any = json.loads(content)
        return InstructionPayload.model_validate(raw)
    except (json.JSONDecodeError, ValidationError) as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Groq returned an invalid instruction JSON payload",
        ) from exc


def validate_instruction_contract(instruction: InstructionPayload) -> None:
    endpoint = instruction.endpoint.strip()
    method = instruction.method.strip().upper()
    params = instruction.params

    if endpoint in {"/tasks", "/tasks/"}:
        if method == "GET":
            return
        if method == "POST":
            try:
                TaskCreate.model_validate(params)
                return
            except ValidationError as exc:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=exc.errors(),
                ) from exc

    match = TASK_ITEM_ENDPOINT.fullmatch(endpoint)
    if match:
        if method == "PUT":
            try:
                TaskReplace.model_validate(params)
                return
            except ValidationError as exc:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=exc.errors(),
                ) from exc
        if method == "PATCH":
            try:
                TaskUpdate.model_validate(params)
                return
            except ValidationError as exc:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=exc.errors(),
                ) from exc
        if method == "DELETE":
            return

    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=(
            "Instruction does not map to supported task routes. "
            "Use: GET /tasks, POST /tasks, PUT|PATCH|DELETE /tasks/{task_id}."
        ),
    )


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
