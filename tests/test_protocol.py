"""MAA 远程控制协议端点的测试。"""

from __future__ import annotations

import base64

from sqlalchemy import select

from maa_remote.config import generate_user_key
from maa_remote.db import SessionLocal
from maa_remote.models import Device, Task, TaskStatus, User
from maa_remote.security import hash_password
from maa_remote.services.tasks import enqueue_task

PNG_1X1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)


def create_user(username: str = "tester", password: str = "password123") -> int:
    db = SessionLocal()
    try:
        user = User(username=username, password_hash=hash_password(password), user_key=generate_user_key())
        db.add(user)
        db.commit()
        return user.id
    finally:
        db.close()


def user_key_of(user_id: int) -> str:
    db = SessionLocal()
    try:
        return db.get(User, user_id).user_key
    finally:
        db.close()


def test_unknown_user_key_is_rejected(client):
    response = client.post("/maa/getTask", json={"user": "not-a-key", "device": "dev-1"})
    assert response.status_code == 401


def test_empty_tasks_when_queue_is_empty(client, db_session):
    user_id = create_user()

    response = client.post("/maa/getTask", json={"user": user_key_of(user_id), "device": "dev-1"})

    assert response.status_code == 200
    assert response.json() == {"tasks": []}

    device = db_session.scalar(select(Device).where(Device.device_uid == "dev-1"))
    assert device is not None
    assert device.user_id == user_id
    assert device.is_online is True


def test_task_is_delivered_only_once_and_reported(client, db_session):
    user_id = create_user()
    key = user_key_of(user_id)

    client.post("/maa/getTask", json={"user": key, "device": "dev-1"})
    device = db_session.scalar(select(Device).where(Device.device_uid == "dev-1"))
    task = enqueue_task(db_session, device, "LinkStart")

    first = client.post("/maa/getTask", json={"user": key, "device": "dev-1"}).json()
    assert [item["id"] for item in first["tasks"]] == [task.id]
    assert first["tasks"][0]["type"] == "LinkStart"

    # 已下发的任务不会重复下发
    second = client.post("/maa/getTask", json={"user": key, "device": "dev-1"}).json()
    assert second["tasks"] == []

    response = client.post(
        "/maa/reportStatus",
        json={
            "user": key,
            "device": "dev-1",
            "task": task.id,
            "status": "SUCCESS",
            "payload": "",
        },
    )
    assert response.status_code == 200

    db_session.expire_all()
    assert db_session.get(Task, task.id).status == TaskStatus.SUCCESS


def test_settings_task_requires_params(client, db_session):
    import pytest

    from maa_remote.services.tasks import TaskError

    user_id = create_user()
    client.post("/maa/getTask", json={"user": user_key_of(user_id), "device": "dev-1"})
    device = db_session.scalar(select(Device).where(Device.device_uid == "dev-1"))

    with pytest.raises(TaskError):
        enqueue_task(db_session, device, "Settings-Stage1", "")


def test_screenshot_is_saved_and_served(client, db_session):
    user_id = create_user()
    key = user_key_of(user_id)
    client.post("/maa/getTask", json={"user": key, "device": "dev-1"})
    device = db_session.scalar(select(Device).where(Device.device_uid == "dev-1"))
    task = enqueue_task(db_session, device, "CaptureImageNow")

    client.post("/maa/getTask", json={"user": key, "device": "dev-1"})

    payload = "data:image/png;base64," + base64.b64encode(PNG_1X1).decode()
    response = client.post(
        "/maa/reportStatus",
        json={"user": key, "device": "dev-1", "task": task.id, "status": "SUCCESS", "payload": payload},
    )
    assert response.status_code == 200

    db_session.expire_all()
    saved = db_session.get(Task, task.id)
    assert saved.screenshot_name == f"{task.id}.png"
    assert saved.payload_size == len(PNG_1X1)

    from maa_remote.config import settings as app_settings

    assert (app_settings.screenshot_dir / saved.screenshot_name).read_bytes() == PNG_1X1


def test_report_for_unknown_task_is_404(client):
    user_id = create_user()
    key = user_key_of(user_id)
    client.post("/maa/getTask", json={"user": key, "device": "dev-1"})

    response = client.post(
        "/maa/reportStatus",
        json={"user": key, "device": "dev-1", "task": "missing", "status": "SUCCESS", "payload": ""},
    )
    assert response.status_code == 404


def test_poll_without_device_is_treated_as_connection_test(client):
    """MAA 设置页的「测试连接」只带 user，不带 device，必须返回 200 而不是 400。"""

    user_id = create_user()
    response = client.post("/maa/getTask", json={"user": user_key_of(user_id)})

    assert response.status_code == 200
    assert response.json() == {"tasks": []}
