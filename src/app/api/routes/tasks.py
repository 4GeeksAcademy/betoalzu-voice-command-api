from fastapi import APIRouter, HTTPException, status

from src.app.schemas.voice import Task, TaskCreate, TaskReplace, TaskUpdate

router = APIRouter(prefix="/tasks", tags=["tasks"])

# In-memory storage for task data.
task: list[Task] = []


@router.get("", response_model=list[Task])
def get_tasks() -> list[Task]:
    return task


@router.post("", response_model=Task, status_code=status.HTTP_201_CREATED)
def create_task(payload: TaskCreate) -> Task:
    new_task = Task(
        id=(task[-1].id + 1) if task else 1,
        title=payload.title,
        done=payload.done,
    )
    task.append(new_task)
    return new_task


@router.put("/{task_id}", response_model=Task)
def replace_task(
    task_id: int,
    payload: TaskReplace,
) -> Task:
    index = find_task_index(task_id)
    if index is None:
        raise_task_not_found(task_id)

    updated_task = Task(id=task_id, title=payload.title, done=payload.done)
    task[index] = updated_task
    return updated_task


@router.patch("/{task_id}", response_model=Task)
def update_task(
    task_id: int,
    payload: TaskUpdate,
) -> Task:
    index = find_task_index(task_id)
    if index is None:
        raise_task_not_found(task_id)

    current_task = task[index]
    updated_task = Task(
        id=current_task.id,
        title=payload.title if payload.title is not None else current_task.title,
        done=payload.done if payload.done is not None else current_task.done,
    )
    task[index] = updated_task
    return updated_task


@router.delete("/{task_id}")
def delete_task(task_id: int) -> dict[str, str]:
    index = find_task_index(task_id)
    if index is None:
        raise_task_not_found(task_id)

    task.pop(index)
    return {"message": f"Task {task_id} deleted successfully"}


def find_task_index(task_id: int) -> int | None:
    for index, item in enumerate(task):
        if item.id == task_id:
            return index
    return None


def raise_task_not_found(task_id: int) -> None:
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Task with id {task_id} not found",
    )
