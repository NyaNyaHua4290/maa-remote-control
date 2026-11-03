"""管理员后台：用户列表、新建、禁用/启用、重置密码、删除。

第一个注册的账号会自动成为管理员（见 pages.register_submit 与 db._ensure_admin_exists）。
"""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import generate_user_key
from ..db import get_db
from ..models import Device, User
from ..security import (
    current_user_optional,
    get_csrf_token,
    hash_password,
    validate_password,
    validate_username,
    verify_csrf,
)
from ..web import templates
from .pages import LoginRequired, _ctx, _redirect

router = APIRouter(tags=["管理员"])
logger = logging.getLogger(__name__)


class AdminRequired(Exception):
    """非管理员访问后台时抛出，由全局异常处理器渲染 403 页面。"""


def _guard(user: User | None) -> User:
    if user is None:
        raise LoginRequired("/admin/users")
    if not user.is_admin:
        raise AdminRequired()
    return user


@router.get("/admin/users")
def admin_users(
    request: Request,
    user: Annotated[User | None, Depends(current_user_optional)],
    db: Annotated[Session, Depends(get_db)],
):
    _guard(user)

    device_counts = dict(
        db.execute(
            select(Device.user_id, func.count(Device.id)).group_by(Device.user_id)
        ).all()
    )
    users = list(db.scalars(select(User).order_by(User.id)).all())
    active_admins = sum(1 for u in users if u.is_admin and u.is_active)

    return templates.TemplateResponse(
        request,
        "admin.html",
        _ctx(
            request,
            user,
            users=users,
            device_counts=device_counts,
            active_admins=active_admins,
            msg=request.query_params.get("msg"),
            err=request.query_params.get("err"),
        ),
    )


@router.post("/admin/users")
def admin_create_user(
    request: Request,
    user: Annotated[User | None, Depends(current_user_optional)],
    db: Annotated[Session, Depends(get_db)],
    username: Annotated[str, Form()] = "",
    password: Annotated[str, Form()] = "",
    is_admin: Annotated[str, Form()] = "",
    csrf_token: Annotated[str, Form()] = "",
):
    _guard(user)
    verify_csrf(request, csrf_token)

    try:
        username = validate_username(username)
        validate_password(password)
    except ValueError as exc:
        return _redirect("/admin/users", err=str(exc))

    if db.scalar(select(User).where(User.username == username)) is not None:
        return _redirect("/admin/users", err="该用户名已被占用")

    new_user = User(
        username=username,
        password_hash=hash_password(password),
        user_key=generate_user_key(),
        is_admin=bool(is_admin),
    )
    db.add(new_user)
    db.commit()
    logger.info("管理员 %s 新建用户 %s", user.username, username)
    return _redirect("/admin/users", msg=f"已创建用户 {username}")


@router.post("/admin/users/{user_id}/toggle")
def admin_toggle_user(
    request: Request,
    user_id: int,
    user: Annotated[User | None, Depends(current_user_optional)],
    db: Annotated[Session, Depends(get_db)],
    csrf_token: Annotated[str, Form()] = "",
):
    admin = _guard(user)
    verify_csrf(request, csrf_token)

    target = db.get(User, user_id)
    if target is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在")
    if target.id == admin.id:
        return _redirect("/admin/users", err="不能禁用自己")

    target.is_active = not target.is_active
    db.commit()
    state = "启用" if target.is_active else "禁用"
    logger.info("管理员 %s %s了用户 %s", admin.username, state, target.username)
    return _redirect("/admin/users", msg=f"已{state} {target.username}")


@router.post("/admin/users/{user_id}/password")
def admin_reset_password(
    request: Request,
    user_id: int,
    user: Annotated[User | None, Depends(current_user_optional)],
    db: Annotated[Session, Depends(get_db)],
    new_password: Annotated[str, Form()] = "",
    csrf_token: Annotated[str, Form()] = "",
):
    admin = _guard(user)
    verify_csrf(request, csrf_token)

    target = db.get(User, user_id)
    if target is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在")

    try:
        validate_password(new_password)
    except ValueError as exc:
        return _redirect("/admin/users", err=str(exc))

    target.password_hash = hash_password(new_password)
    db.commit()
    logger.info("管理员 %s 重置了用户 %s 的密码", admin.username, target.username)
    return _redirect("/admin/users", msg=f"已重置 {target.username} 的密码")


@router.post("/admin/users/{user_id}/delete")
def admin_delete_user(
    request: Request,
    user_id: int,
    user: Annotated[User | None, Depends(current_user_optional)],
    db: Annotated[Session, Depends(get_db)],
    csrf_token: Annotated[str, Form()] = "",
):
    admin = _guard(user)
    verify_csrf(request, csrf_token)

    target = db.get(User, user_id)
    if target is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在")
    if target.id == admin.id:
        return _redirect("/admin/users", err="不能删除自己")

    if target.is_admin:
        remaining_admins = db.scalar(
            select(func.count()).select_from(User).where(User.is_admin.is_(True), User.id != target.id)
        )
        if not remaining_admins:
            return _redirect("/admin/users", err="至少要保留一个管理员")

    username = target.username
    db.delete(target)  # devices / tasks 由 ORM 的级联删除一并清理
    db.commit()
    logger.info("管理员 %s 删除了用户 %s", admin.username, username)
    return _redirect("/admin/users", msg=f"已删除用户 {username}")
