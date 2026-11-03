"""管理员功能测试：首个账号成为管理员、用户管理操作、权限边界。"""

from __future__ import annotations

import re

from sqlalchemy import select

from maa_remote.db import SessionLocal
from maa_remote.models import Device, User

CSRF_PATTERN = re.compile(r'name="csrf_token" value="([^"]+)"')


def _csrf(client, url: str, follow_redirects: bool = True) -> str:
    response = client.get(url, follow_redirects=follow_redirects)
    match = CSRF_PATTERN.search(response.text)
    assert match, f"{url} 没有 csrf_token"
    return match.group(1)


def _register(client, username: str, password: str = "password123"):
    token = _csrf(client, "/register")
    return client.post(
        "/register",
        data={"username": username, "password": password, "password2": password, "csrf_token": token},
        follow_redirects=False,
    )


def _login(client, username: str, password: str = "password123"):
    token = _csrf(client, "/login")
    return client.post(
        "/login",
        data={"username": username, "password": password, "csrf_token": token, "next": "/"},
        follow_redirects=False,
    )


def _user(username: str) -> User:
    db = SessionLocal()
    try:
        user = db.scalar(select(User).where(User.username == username))
        assert user is not None
        db.expunge(user)
        return user
    finally:
        db.close()


def test_first_registered_user_is_admin(client):
    _register(client, "owner")
    assert _user("owner").is_admin is True

    client.post("/logout", data={"csrf_token": _csrf(client, "/")}, follow_redirects=False)
    _register(client, "guest")
    assert _user("guest").is_admin is False


def test_admin_page_visible_only_to_admin(client):
    _register(client, "owner")
    page = client.get("/admin/users")
    assert page.status_code == 200
    assert "用户管理" in page.text

    client.post("/logout", data={"csrf_token": _csrf(client, "/")}, follow_redirects=False)
    _register(client, "guest")

    forbidden = client.get("/admin/users")
    assert forbidden.status_code == 403
    assert "只有管理员" in forbidden.text


def test_admin_can_create_disable_and_delete_user(client):
    _register(client, "owner")
    token = _csrf(client, "/admin/users")

    created = client.post(
        "/admin/users",
        data={"username": "worker", "password": "password123", "csrf_token": token},
        follow_redirects=False,
    )
    assert created.status_code == 303
    worker = _user("worker")
    assert worker.is_admin is False

    toggled = client.post(
        f"/admin/users/{worker.id}/toggle",
        data={"csrf_token": token},
        follow_redirects=False,
    )
    assert toggled.status_code == 303
    state = SessionLocal()
    try:
        assert state.get(User, worker.id).is_active is False
    finally:
        state.close()

    # 被禁用的账号无法登录
    client.post("/logout", data={"csrf_token": _csrf(client, "/")}, follow_redirects=False)
    blocked = _login(client, "worker")
    assert blocked.status_code == 403
    assert "禁用" in blocked.text

    _login(client, "owner")
    token = _csrf(client, "/admin/users")
    deleted = client.post(
        f"/admin/users/{worker.id}/delete",
        data={"csrf_token": token},
        follow_redirects=False,
    )
    assert deleted.status_code == 303
    db = SessionLocal()
    try:
        assert db.get(User, worker.id) is None
    finally:
        db.close()


def test_admin_cannot_disable_or_delete_self(client):
    _register(client, "owner")
    owner = _user("owner")
    token = _csrf(client, "/admin/users")

    client.post(f"/admin/users/{owner.id}/toggle", data={"csrf_token": token}, follow_redirects=False)
    assert SessionLocal().get(User, owner.id).is_active is True

    client.post(f"/admin/users/{owner.id}/delete", data={"csrf_token": token}, follow_redirects=False)
    assert _user("owner") is not None


def test_admin_password_reset(client):
    _register(client, "owner")
    token = _csrf(client, "/admin/users")
    client.post(
        "/admin/users",
        data={"username": "worker", "password": "password123", "csrf_token": token},
        follow_redirects=False,
    )
    worker = _user("worker")

    reset = client.post(
        f"/admin/users/{worker.id}/password",
        data={"new_password": "newpassword456", "csrf_token": token},
        follow_redirects=False,
    )
    assert reset.status_code == 303

    client.post("/logout", data={"csrf_token": _csrf(client, "/")}, follow_redirects=False)
    assert _login(client, "worker", "newpassword456").status_code == 303


def test_deleting_user_removes_devices(client):
    _register(client, "owner")
    token = _csrf(client, "/admin/users")
    client.post(
        "/admin/users",
        data={"username": "worker", "password": "password123", "csrf_token": token},
        follow_redirects=False,
    )
    worker = _user("worker")

    db = SessionLocal()
    try:
        db.add(Device(user_id=worker.id, device_uid="dev-x"))
        db.commit()
    finally:
        db.close()

    client.post(f"/admin/users/{worker.id}/delete", data={"csrf_token": token}, follow_redirects=False)

    db = SessionLocal()
    try:
        assert db.scalar(select(Device).where(Device.device_uid == "dev-x")) is None
    finally:
        db.close()


def test_admin_actions_require_csrf(client):
    _register(client, "owner")
    worker_id = _user("owner").id

    response = client.post(f"/admin/users/{worker_id}/toggle", data={})
    assert response.status_code == 403
