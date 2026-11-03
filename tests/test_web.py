"""网页流程测试：注册、登录、下发任务、重命名。"""

from __future__ import annotations

import re

from sqlalchemy import select

from maa_remote.db import SessionLocal
from maa_remote.models import Device, Task, User

CSRF_PATTERN = re.compile(r'name="csrf_token" value="([^"]+)"')


def _csrf(client, url: str) -> str:
    response = client.get(url)
    assert response.status_code == 200, response.text
    match = CSRF_PATTERN.search(response.text)
    assert match, f"{url} 页面里没有找到 csrf_token"
    return match.group(1)


def _register(client, username: str = "alice", password: str = "password123"):
    token = _csrf(client, "/register")
    return client.post(
        "/register",
        data={"username": username, "password": password, "password2": password, "csrf_token": token},
        follow_redirects=False,
    )


def test_dashboard_requires_login(client):
    response = client.get("/", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"].startswith("/login")


def test_register_then_see_dashboard(client):
    response = _register(client)
    assert response.status_code == 303
    assert response.headers["location"] == "/setup"

    dashboard = client.get("/")
    assert dashboard.status_code == 200
    assert "我的 MAA 实例" in dashboard.text
    assert "alice" in dashboard.text


def test_register_rejects_short_password(client):
    token = _csrf(client, "/register")
    response = client.post(
        "/register",
        data={"username": "bob", "password": "123", "password2": "123", "csrf_token": token},
    )
    assert response.status_code == 400
    assert "至少" in response.text


def test_login_and_logout(client):
    _register(client, username="carol")
    token = _csrf(client, "/")
    logout = client.post("/logout", data={"csrf_token": token}, follow_redirects=False)
    assert logout.headers["location"] == "/login"

    assert client.get("/", follow_redirects=False).status_code == 303

    token = _csrf(client, "/login")
    login = client.post(
        "/login",
        data={"username": "carol", "password": "password123", "csrf_token": token, "next": "/"},
        follow_redirects=False,
    )
    assert login.status_code == 303
    assert login.headers["location"] == "/"
    assert client.get("/").status_code == 200


def test_enqueue_task_and_rename_device(client):
    _register(client, username="dave")

    db = SessionLocal()
    try:
        user = db.scalar(select(User).where(User.username == "dave"))
        key = user.user_key
    finally:
        db.close()

    # 模拟 MAA 首次轮询，自动登记设备
    assert client.post("/maa/getTask", json={"user": key, "device": "device-xyz"}).status_code == 200

    db = SessionLocal()
    device = db.scalar(select(Device).where(Device.device_uid == "device-xyz"))
    device_id = device.id
    db.close()

    token = _csrf(client, f"/devices/{device_id}")
    response = client.post(
        f"/devices/{device_id}/tasks",
        data={"type": "LinkStart", "params": "", "csrf_token": token},
        follow_redirects=False,
    )
    assert response.status_code == 303

    db = SessionLocal()
    task = db.scalar(select(Task).where(Task.device_id == device_id))
    assert task is not None
    assert task.type == "LinkStart"
    db.close()

    response = client.post(
        f"/devices/{device_id}/rename",
        data={"name": "官服", "csrf_token": token},
        follow_redirects=False,
    )
    assert response.status_code == 303

    page = client.get(f"/devices/{device_id}")
    assert "官服" in page.text


def test_task_form_without_csrf_is_rejected(client):
    _register(client, username="erin")

    db = SessionLocal()
    user = db.scalar(select(User).where(User.username == "erin"))
    key = user.user_key
    db.close()

    client.post("/maa/getTask", json={"user": key, "device": "dev-2"})
    db = SessionLocal()
    device_id = db.scalar(select(Device).where(Device.device_uid == "dev-2")).id
    db.close()

    response = client.post(f"/devices/{device_id}/tasks", data={"type": "LinkStart", "params": ""})
    assert response.status_code == 403


def test_api_devices_requires_login(client):
    assert client.get("/api/devices").status_code == 401


def test_healthz(client):
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
