"""给前端页面用的 JSON 接口（只读，方便页面轮询刷新）。"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Device, Task, User
from ..security import require_user
from ..services import tasks as task_service
from ..services.devices import get_device, list_devices

router = APIRouter(prefix="/api", tags=["页面接口"])


def _device_dict(device: Device) -> dict:
    return {
        "id": device.id,
        "name": device.display_name,
        "device_uid": device.device_uid,
        "online": device.is_online,
        "last_seen_at": device.last_seen_at.isoformat() if device.last_seen_at else None,
    }


def _task_dict(task: Task) -> dict:
    return {
        "id": task.id,
        "type": task.type,
        "params": task.params,
        "status": task.status,
        "created_at": task.created_at.isoformat() if task.created_at else None,
        "finished_at": task.finished_at.isoformat() if task.finished_at else None,
        "has_screenshot": task.has_screenshot,
        "error_message": task.error_message,
    }


@router.get("/devices")
def api_devices(
    user: Annotated[User, Depends(require_user)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    return {"devices": [_device_dict(d) for d in list_devices(db, user)]}


@router.get("/devices/{device_id}")
def api_device(
    device_id: int,
    user: Annotated[User, Depends(require_user)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    device = get_device(db, user, device_id)
    if device is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="设备不存在")

    tasks = task_service.device_tasks(db, device, limit=30)
    return {
        "device": _device_dict(device),
        "pending": task_service.pending_count(db, device),
        "tasks": [_task_dict(t) for t in tasks],
    }
