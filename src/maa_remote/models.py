"""ORM 模型：用户、MAA 实例（设备）、任务。"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from enum import StrEnum

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .config import ONLINE_THRESHOLD_SECONDS
from .db import Base


def utcnow() -> datetime:
    """统一使用「不带时区的 UTC 时间」存库，避免 SQLite 时区差异。"""

    return datetime.now(timezone.utc).replace(tzinfo=None)


class TaskStatus(StrEnum):
    PENDING = "pending"      # 等待 MAA 拉取
    DELIVERED = "delivered"  # 已下发给 MAA，等待回报
    SUCCESS = "success"
    FAILED = "failed"
    TIMEOUT = "timeout"      # 下发后长时间没回报
    CANCELED = "canceled"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    # 填到 MAA「用户标识符」里的随机密钥，相当于 MAA 的访问口令
    user_key: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    # 首个注册的账号自动成为管理员
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)

    devices: Mapped[list["Device"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        order_by="Device.created_at",
    )


class Device(Base):
    """一台被控 MAA 实例。MAA 每次轮询都会带上自动生成的设备标识符。"""

    __tablename__ = "devices"
    __table_args__ = (UniqueConstraint("user_id", "device_uid", name="uq_devices_user_device_uid"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    device_uid: Mapped[str] = mapped_column(String(128))
    name: Mapped[str] = mapped_column(String(64), default="")
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_ip: Mapped[str] = mapped_column(String(64), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    user: Mapped[User] = relationship(back_populates="devices")
    tasks: Mapped[list["Task"]] = relationship(
        back_populates="device",
        cascade="all, delete-orphan",
        order_by="Task.created_at.desc()",
    )

    @property
    def display_name(self) -> str:
        return self.name or f"MAA-{self.device_uid[:8]}"

    @property
    def is_online(self) -> bool:
        if self.last_seen_at is None:
            return False
        return utcnow() - self.last_seen_at <= timedelta(seconds=ONLINE_THRESHOLD_SECONDS)


class Task(Base):
    """下发给 MAA 的一条任务，id 直接对应该协议里的 task id。"""

    __tablename__ = "tasks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    device_id: Mapped[int] = mapped_column(ForeignKey("devices.id", ondelete="CASCADE"), index=True)
    type: Mapped[str] = mapped_column(String(64))
    # Settings-* 类任务需要带 params，例如 Settings-Stage1 要传关卡名
    params: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default=TaskStatus.PENDING, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # 截图类任务把 base64 落盘，只在库里记文件名和体积
    screenshot_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    payload_size: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    device: Mapped[Device] = relationship(back_populates="tasks")

    @property
    def is_finished(self) -> bool:
        return self.status in {
            TaskStatus.SUCCESS,
            TaskStatus.FAILED,
            TaskStatus.TIMEOUT,
            TaskStatus.CANCELED,
        }

    @property
    def has_screenshot(self) -> bool:
        return bool(self.screenshot_name)
