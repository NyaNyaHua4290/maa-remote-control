"""MAA 实例（设备）的记录与查询。"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Device, User, utcnow


def upsert_device(db: Session, user: User, device_uid: str, ip: str = "") -> Device:
    """MAA 每次轮询都会带上设备标识符；第一次见到就自动登记。"""

    device_uid = (device_uid or "").strip()
    if not device_uid:
        raise ValueError("device 不能为空")

    device = db.scalar(
        select(Device).where(Device.user_id == user.id, Device.device_uid == device_uid)
    )
    if device is None:
        device = Device(user_id=user.id, device_uid=device_uid)
        db.add(device)

    device.last_seen_at = utcnow()
    device.last_ip = ip or device.last_ip
    db.commit()
    db.refresh(device)
    return device


def list_devices(db: Session, user: User) -> list[Device]:
    return list(
        db.scalars(select(Device).where(Device.user_id == user.id).order_by(Device.created_at)).all()
    )


def get_device(db: Session, user: User, device_id: int) -> Device | None:
    return db.scalar(select(Device).where(Device.id == device_id, Device.user_id == user.id))
