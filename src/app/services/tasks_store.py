"""In-memory storage for tasks.

This module owns the single source of truth for task data: a plain
Python list living at module scope. No database, no file persistence.
Data resets whenever the server restarts, which is expected for this
project.
"""

from src.app.schemas.voice import Task, TaskCreate, TaskReplace, TaskUpdate

_tasks: list[Task] = []
_next_id: int = 1


def list_tasks() -> list[Task]:
    return list(_tasks)


def create_task(payload: TaskCreate) -> Task:
    global _next_id
    task = Task(id=_next_id, title=payload.title, done=payload.done)
    _tasks.append(task)
    _next_id += 1
    return task


def get_task(task_id: int) -> Task | None:
    return next((t for t in _tasks if t.id == task_id), None)


def replace_task(task_id: int, payload: TaskReplace) -> Task | None:
    for index, existing in enumerate(_tasks):
        if existing.id == task_id:
            updated = Task(id=task_id, title=payload.title, done=payload.done)
            _tasks[index] = updated
            return updated
    return None


def update_task(task_id: int, payload: TaskUpdate) -> Task | None:
    for index, existing in enumerate(_tasks):
        if existing.id == task_id:
            changes = payload.model_dump(exclude_unset=True, exclude_none=True)
            updated = existing.model_copy(update=changes)
            _tasks[index] = updated
            return updated
    return None


def delete_task(task_id: int) -> bool:
    for index, existing in enumerate(_tasks):
        if existing.id == task_id:
            _tasks.pop(index)
            return True
    return False