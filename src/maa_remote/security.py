"""密码、会话与 CSRF 相关的辅助函数。"""

from __future__ import annotations

import re
import secrets
from typing import Annotated

import bcrypt
from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from .db import get_db
from .models import User

USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9_\-\u4e00-\u9fa5]{3,32}$")
MIN_PASSWORD_LENGTH = 8
# bcrypt 只处理前 72 字节
MAX_PASSWORD_LENGTH = 72

SESSION_USER_KEY = "user_id"
SESSION_CSRF_KEY = "csrf_token"


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def validate_username(username: str) -> str:
    username = username.strip()
    if not USERNAME_PATTERN.match(username):
        raise ValueError("用户名需为 3-32 位中文、字母、数字、下划线或短横线")
    return username


def validate_password(password: str) -> None:
    if len(password) < MIN_PASSWORD_LENGTH:
        raise ValueError(f"密码至少 {MIN_PASSWORD_LENGTH} 位")
    if len(password.encode("utf-8")) > MAX_PASSWORD_LENGTH:
        raise ValueError(f"密码不能超过 {MAX_PASSWORD_LENGTH} 字节")


def get_csrf_token(request: Request) -> str:
    """取出（或首次生成）当前会话的 CSRF token。"""

    token = request.session.get(SESSION_CSRF_KEY)
    if not token:
        token = secrets.token_urlsafe(32)
        request.session[SESSION_CSRF_KEY] = token
    return token


def verify_csrf(request: Request, token: str | None) -> None:
    expected = request.session.get(SESSION_CSRF_KEY)
    if not expected or not token or not secrets.compare_digest(str(expected), str(token)):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="CSRF 校验失败，请刷新页面重试")


def login_user(request: Request, user: User) -> None:
    request.session.clear()
    request.session[SESSION_USER_KEY] = user.id


def logout_user(request: Request) -> None:
    request.session.clear()


def current_user_optional(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
) -> User | None:
    user_id = request.session.get(SESSION_USER_KEY)
    if not user_id:
        return None
    user = db.get(User, user_id)
    if user is None or not user.is_active:
        request.session.clear()
        return None
    return user


def require_user(
    user: Annotated[User | None, Depends(current_user_optional)],
) -> User:
    """接口用：未登录直接 401。"""

    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="请先登录")
    return user


def find_user_by_key(db: Session, user_key: str) -> User | None:
    return db.scalar(select(User).where(User.user_key == user_key, User.is_active.is_(True)))
