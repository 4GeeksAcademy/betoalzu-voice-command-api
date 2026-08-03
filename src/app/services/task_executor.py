"""Executes a routing InstructionPayload against the in-memory task store.

Used by /transcribe to turn a routing decision into an actual result,
without making an internal HTTP call back into the API.
"""

import re

from fastapi import HTTPException, status

from src.app.schemas.voice import InstructionPayload, TaskCreate, TaskReplace, TaskUpdate
from src.app.services import tasks_store

_TASK_ID_PATTERN = re.compile(r"^/tasks/(\d+)$")


def execute_instruction(instruction: InstructionPayload) -> dict | list | None:
    method = instruction.method.upper()
    endpoint = instruction.endpoint
    params = instruction.params or {}

    if endpoint == "/tasks" and method == "GET":
        return [task.model_dump() for task in tasks_store.list_tasks()]

    if endpoint == "/tasks" and method == "POST":
        payload = TaskCreate(title=params.get("title", ""), done=params.get("done", False))
        return tasks_store.create_task(payload).model_dump()

    match = _TASK_ID_PATTERN.match(endpoint)
    task_id = match.group(1) if match else params.get("task_id")

    if task_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Could not resolve a task id for instruction endpoint '{endpoint}'.",
        )
    task_id = int(task_id)

    if method == "PUT":
        payload = TaskReplace(title=params.get("title", ""), done=params.get("done", False))
        result = tasks_store.replace_task(task_id, payload)
    elif method == "PATCH":
        payload = TaskUpdate(title=params.get("title"), done=params.get("done"))
        result = tasks_store.update_task(task_id, payload)
    elif method == "DELETE":
        deleted = tasks_store.delete_task(task_id)
        if not deleted:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Task {task_id} not found",
            )
        return {"message": f"Task {task_id} deleted"}
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported instruction method '{method}'.",
        )

    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Task {task_id} not found",
        )
    return result.model_dump()