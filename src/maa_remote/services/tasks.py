"""任务队列：入队、下发、回报、超时回收。"""

from __future__ import annotations

from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import SUPPORTED_TASK_TYPES, TASK_TIMEOUT_MINUTES
from ..models import Device, Task, TaskStatus, utcnow

# 单次轮询最多返回多少条任务，避免一次塞太多给 MAA
MAX_TASKS_PER_POLL = 20


class TaskError(ValueError):
    """任务参数不合法。"""


def enqueue_task(db: Session, device: Device, task_type: str, params: str | None = None) -> Task:
    if task_type not in SUPPORTED_TASK_TYPES:
        raise TaskError(f"不支持的任务类型：{task_type}")

    normalized_params = (params or "").strip() or None
    if task_type.startswith("Settings-") and normalized_params is None:
        raise TaskError("Settings 类任务必须提供 params")

    task = Task(
        user_id=device.user_id,
        device_id=device.id,
        type=task_type,
        params=normalized_params,
        status=TaskStatus.PENDING,
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


def claim_pending_tasks(db: Session, device: Device, limit: int = MAX_TASKS_PER_POLL) -> list[Task]:
    """取出待执行任务并标记为已下发。

    MAA 自己会按 id 去重，所以这里只把「从未下发过」的任务交出去，
    避免 MAA 重启丢掉记忆后重复执行旧任务。
    """

    expire_stale_tasks(db)

    tasks = list(
        db.scalars(
            select(Task)
            .where(Task.device_id == device.id, Task.status == TaskStatus.PENDING)
            .order_by(Task.created_at)
            .limit(limit)
        ).all()
    )
    if tasks:
        now = utcnow()
        for task in tasks:
            task.status = TaskStatus.DELIVERED
            task.delivered_at = now
        db.commit()
    return tasks


def expire_stale_tasks(db: Session, minutes: int = TASK_TIMEOUT_MINUTES) -> int:
    """把下发后长时间没有回报的任务标记为超时。"""

    deadline = utcnow() - timedelta(minutes=minutes)
    stale = list(
        db.scalars(
            select(Task).where(Task.status == TaskStatus.DELIVERED, Task.delivered_at < deadline)
        ).all()
    )
    for task in stale:
        task.status = TaskStatus.TIMEOUT
        task.finished_at = utcnow()
        task.error_message = f"下发后 {minutes} 分钟内未收到 MAA 回报"
    if stale:
        db.commit()
    return len(stale)


def record_report(db: Session, task: Task, reported_status: str, payload: str = "") -> Task:
    """记录 MAA 的回报结果。"""

    ok = (reported_status or "").strip().upper() == "SUCCESS"
    task.status = TaskStatus.SUCCESS if ok else TaskStatus.FAILED
    task.finished_at = utcnow()
    task.payload_size = len(payload or "")
    if not ok:
        task.error_message = (payload or "")[:2000] or "MAA 回报任务失败"
    db.commit()
    db.refresh(task)
    return task


def device_tasks(db: Session, device: Device, limit: int = 50) -> list[Task]:
    return list(
        db.scalars(
            select(Task)
            .where(Task.device_id == device.id)
            .order_by(Task.created_at.desc())
            .limit(limit)
        ).all()
    )


def pending_count(db: Session, device: Device) -> int:
    return len(
        db.scalars(
            select(Task.id).where(
                Task.device_id == device.id,
                Task.status.in_([TaskStatus.PENDING, TaskStatus.DELIVERED]),
            )
        ).all()
    )
