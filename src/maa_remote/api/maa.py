"""MAA 官方远程控制协议的两个端点。

协议文档：https://docs.maa.plus/zh-cn/protocol/remote-control-schema.html

这两个端点必须是匿名可访问的：MAA 只会在请求体里带 `user`（用户标识符，
即本站用户的 user_key）和 `device`（MAA 自动生成的设备标识符）。
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Device, Task
from ..security import find_user_by_key
from ..services import tasks as task_service
from ..services.devices import upsert_device
from ..services.screenshots import ScreenshotError, save_screenshot

logger = logging.getLogger(__name__)

router = APIRouter(tags=["MAA 协议"])

SCREENSHOT_TASK_TYPES = {"CaptureImage", "CaptureImageNow"}


class MaaPollRequest(BaseModel):
    user: str = ""
    device: str = ""


class MaaReportRequest(MaaPollRequest):
    task: str = ""
    status: str = "SUCCESS"
    payload: str = ""


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else ""


@router.post("/maa/getTask")
def get_task(
    body: MaaPollRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> dict:
    """MAA 轮询取任务。返回 401 时 MAA 会提示连接测试失败。"""

    user = find_user_by_key(db, body.user.strip())
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户标识符无效")

    device_uid = (body.device or "").strip()
    if not device_uid:
        # MAA 设置页的「测试连接」只带 user、不带 device，
        # 这里直接返回空任务让它测通，不要报 400（否则 MAA 会显示 BadRequest）
        return {"tasks": []}

    device = upsert_device(db, user, device_uid, _client_ip(request))
    tasks = task_service.claim_pending_tasks(db, device)
    if tasks:
        logger.info("向 %s 下发 %d 个任务", device.display_name, len(tasks))

    payload: list[dict] = []
    for task in tasks:
        item = {"id": task.id, "type": task.type}
        if task.params:
            item["params"] = task.params
        payload.append(item)
    return {"tasks": payload}


@router.post("/maa/reportStatus")
def report_status(
    body: MaaReportRequest,
    db: Session = Depends(get_db),
) -> dict:
    """MAA 回报任务结果（截图任务的图片就在 payload 里）。"""

    user = find_user_by_key(db, body.user.strip())
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户标识符无效")

    device = db.scalar(
        select(Device).where(
            Device.user_id == user.id,
            Device.device_uid == body.device.strip(),
        )
    )
    if device is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="设备未登记")

    task = db.get(Task, body.task.strip())
    if task is None or task.device_id != device.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="任务不存在")

    # MAA 有时会重复回报同一个任务，直接忽略
    if task.is_finished:
        return {"ok": True, "duplicated": True}

    task = task_service.record_report(db, task, body.status, body.payload)

    if task.type in SCREENSHOT_TASK_TYPES and body.payload:
        try:
            filename, size = save_screenshot(task.id, body.payload)
        except ScreenshotError as exc:
            logger.warning("截图保存失败：%s", exc)
            task.error_message = f"截图保存失败：{exc}"
        else:
            task.screenshot_name = filename
            task.payload_size = size
        db.commit()

    logger.info(
        "任务回报 %s / %s -> %s", device.display_name, task.type, task.status
    )
    return {"ok": True}
