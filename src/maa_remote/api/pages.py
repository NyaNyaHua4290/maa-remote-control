"""网页页面路由（服务端渲染 + 少量 JSON 轮询）。"""

from __future__ import annotations

import logging
from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import generate_user_key, settings
from ..db import get_db
from ..models import Task, User
from ..security import (
    current_user_optional,
    get_csrf_token,
    hash_password,
    login_user,
    logout_user,
    validate_password,
    validate_username,
    verify_csrf,
    verify_password,
)
from ..services import tasks as task_service
from ..services.devices import get_device, list_devices
from ..services.screenshots import ScreenshotError, screenshot_path
from ..web import templates

router = APIRouter(tags=["页面"])
logger = logging.getLogger(__name__)


class LoginRequired(Exception):
    """未登录访问页面时抛出，由全局异常处理器跳转到登录页。"""

    def __init__(self, next_url: str = "/") -> None:
        self.next_url = next_url


def _safe_next(value: str | None, default: str = "/") -> str:
    if not value or not value.startswith("/") or value.startswith("//"):
        return default
    return value


def _ctx(request: Request, user: User | None, **extra) -> dict:
    context = {"request": request, "user": user, "csrf_token": get_csrf_token(request)}
    context.update(extra)
    return context


def _redirect(url: str, msg: str | None = None, err: str | None = None) -> RedirectResponse:
    if msg:
        url = f"{url}?msg={quote(msg)}"
    elif err:
        url = f"{url}?err={quote(err)}"
    return RedirectResponse(url=url, status_code=status.HTTP_303_SEE_OTHER)


# --------------------------------------------------------------------------- #
# 首页 / 登录 / 注册
# --------------------------------------------------------------------------- #
@router.get("/")
def index(
    request: Request,
    user: Annotated[User | None, Depends(current_user_optional)],
    db: Annotated[Session, Depends(get_db)],
):
    if user is None:
        raise LoginRequired("/")

    devices = list_devices(db, user)
    online = sum(1 for d in devices if d.is_online)
    stats = {"total": len(devices), "online": online}
    return templates.TemplateResponse(
        request, "dashboard.html", _ctx(request, user, devices=devices, stats=stats)
    )


@router.get("/login")
def login_page(
    request: Request,
    user: Annotated[User | None, Depends(current_user_optional)],
    next: str = "/",
):
    if user is not None:
        return RedirectResponse(_safe_next(next), status_code=status.HTTP_303_SEE_OTHER)
    return templates.TemplateResponse(
        request, "login.html", _ctx(request, None, next_url=_safe_next(next))
    )


@router.post("/login")
def login_submit(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    username: Annotated[str, Form()] = "",
    password: Annotated[str, Form()] = "",
    csrf_token: Annotated[str, Form()] = "",
    next: Annotated[str, Form()] = "/",
):
    verify_csrf(request, csrf_token)
    target = _safe_next(next)

    user = db.scalar(select(User).where(User.username == username.strip()))
    if user is None or not verify_password(password, user.password_hash):
        return templates.TemplateResponse(
            request,
            "login.html",
            _ctx(request, None, next_url=target, error="用户名或密码错误"),
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    if not user.is_active:
        return templates.TemplateResponse(
            request,
            "login.html",
            _ctx(request, None, next_url=target, error="该账号已被禁用"),
            status_code=status.HTTP_403_FORBIDDEN,
        )

    login_user(request, user)
    logger.info("用户登录：%s", user.username)
    return RedirectResponse(target, status_code=status.HTTP_303_SEE_OTHER)


@router.get("/register")
def register_page(
    request: Request,
    user: Annotated[User | None, Depends(current_user_optional)],
):
    if user is not None:
        return RedirectResponse("/", status_code=status.HTTP_303_SEE_OTHER)
    if not settings.allow_registration:
        return templates.TemplateResponse(
            request, "error.html", _ctx(request, None, message="本站未开放注册，请联系管理员开通账号"),
            status_code=status.HTTP_403_FORBIDDEN,
        )
    return templates.TemplateResponse(request, "register.html", _ctx(request, None))


@router.post("/register")
def register_submit(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    username: Annotated[str, Form()] = "",
    password: Annotated[str, Form()] = "",
    password2: Annotated[str, Form()] = "",
    csrf_token: Annotated[str, Form()] = "",
):
    verify_csrf(request, csrf_token)
    if not settings.allow_registration:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="本站未开放注册")

    def fail(message: str):
        return templates.TemplateResponse(
            request,
            "register.html",
            _ctx(request, None, error=message, username=username),
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    if password != password2:
        return fail("两次输入的密码不一致")
    try:
        username = validate_username(username)
        validate_password(password)
    except ValueError as exc:
        return fail(str(exc))

    if db.scalar(select(User).where(User.username == username)) is not None:
        return fail("该用户名已被注册")

    user = User(username=username, password_hash=hash_password(password), user_key=generate_user_key())
    db.add(user)
    db.commit()
    db.refresh(user)

    login_user(request, user)
    logger.info("新用户注册：%s", user.username)
    return RedirectResponse("/setup", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/logout")
def logout(
    request: Request,
    csrf_token: Annotated[str, Form()] = "",
):
    verify_csrf(request, csrf_token)
    logout_user(request)
    return RedirectResponse("/login", status_code=status.HTTP_303_SEE_OTHER)


# --------------------------------------------------------------------------- #
# 配置引导
# --------------------------------------------------------------------------- #
@router.get("/setup")
def setup_page(
    request: Request,
    user: Annotated[User | None, Depends(current_user_optional)],
):
    if user is None:
        raise LoginRequired("/setup")
    return templates.TemplateResponse(request, "setup.html", _ctx(request, user))


# --------------------------------------------------------------------------- #
# 设备详情与操作
# --------------------------------------------------------------------------- #
@router.get("/devices/{device_id}")
def device_page(
    request: Request,
    device_id: int,
    user: Annotated[User | None, Depends(current_user_optional)],
    db: Annotated[Session, Depends(get_db)],
):
    if user is None:
        raise LoginRequired(f"/devices/{device_id}")

    device = get_device(db, user, device_id)
    if device is None:
        return templates.TemplateResponse(
            request, "error.html", _ctx(request, user, message="设备不存在"), status_code=404
        )

    context = _ctx(
        request,
        user,
        device=device,
        tasks=task_service.device_tasks(db, device, limit=40),
        pending=task_service.pending_count(db, device),
        task_types=task_type_choices(),
        msg=request.query_params.get("msg"),
        err=request.query_params.get("err"),
    )
    return templates.TemplateResponse(request, "device.html", context)


@router.post("/devices/{device_id}/rename")
def rename_device(
    request: Request,
    device_id: int,
    user: Annotated[User | None, Depends(current_user_optional)],
    db: Annotated[Session, Depends(get_db)],
    name: Annotated[str, Form()] = "",
    csrf_token: Annotated[str, Form()] = "",
):
    if user is None:
        raise LoginRequired(f"/devices/{device_id}")
    verify_csrf(request, csrf_token)

    device = get_device(db, user, device_id)
    if device is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="设备不存在")

    device.name = name.strip()[:32]
    db.commit()
    return _redirect(f"/devices/{device_id}", msg="已重命名")


@router.post("/devices/{device_id}/tasks")
def create_task(
    request: Request,
    device_id: int,
    user: Annotated[User | None, Depends(current_user_optional)],
    db: Annotated[Session, Depends(get_db)],
    type: Annotated[str, Form()] = "",
    params: Annotated[str, Form()] = "",
    csrf_token: Annotated[str, Form()] = "",
):
    if user is None:
        raise LoginRequired(f"/devices/{device_id}")
    verify_csrf(request, csrf_token)

    device = get_device(db, user, device_id)
    if device is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="设备不存在")

    try:
        task_service.enqueue_task(db, device, type.strip(), params)
    except task_service.TaskError as exc:
        return _redirect(f"/devices/{device_id}", err=str(exc))

    return _redirect(f"/devices/{device_id}", msg="任务已加入队列")


@router.get("/devices/{device_id}/screenshot/{task_id}")
def device_screenshot(
    device_id: int,
    task_id: str,
    user: Annotated[User | None, Depends(current_user_optional)],
    db: Annotated[Session, Depends(get_db)],
):
    if user is None:
        raise LoginRequired(f"/devices/{device_id}")

    device = get_device(db, user, device_id)
    if device is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="设备不存在")

    task = db.get(Task, task_id)
    if task is None or task.device_id != device.id or not task.screenshot_name:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="截图不存在")

    try:
        path = screenshot_path(task.screenshot_name)
    except ScreenshotError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    if not path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="截图文件已丢失")
    return FileResponse(path, media_type="image/png", headers={"Cache-Control": "private, max-age=600"})


@router.get("/healthz", include_in_schema=False)
def healthz() -> JSONResponse:
    return JSONResponse({"status": "ok"})


def task_type_choices() -> list[tuple[str, str]]:
    """给模板用的「任务类型下拉框」选项。"""

    from ..config import SUPPORTED_TASK_TYPES
    from ..web import TASK_LABELS

    return [(value, TASK_LABELS.get(value, value)) for value in SUPPORTED_TASK_TYPES]
