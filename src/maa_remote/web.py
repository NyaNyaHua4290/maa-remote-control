"""Jinja2 模板环境与通用过滤器。"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from fastapi.templating import Jinja2Templates

from . import __version__
from .config import settings

TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
STATIC_DIR = Path(__file__).resolve().parent / "static"

STATUS_LABELS = {
    "pending": "等待下发",
    "delivered": "已下发",
    "success": "成功",
    "failed": "失败",
    "timeout": "超时",
    "canceled": "已取消",
}

TASK_LABELS = {
    "LinkStart": "一键长草",
    "LinkStart-Base": "基建换班",
    "LinkStart-WakeUp": "开始唤醒",
    "LinkStart-Combat": "刷理智",
    "LinkStart-Recruiting": "自动公招",
    "LinkStart-Mall": "信用购物",
    "LinkStart-Mission": "领取奖励",
    "LinkStart-AutoRoguelike": "自动肉鸽",
    "Toolbox-GachaOnce": "抽卡（单抽）",
    "Toolbox-GachaTenTimes": "抽卡（十连）",
    "Toolbox-Reclamation": "生息演算",
    "Settings-ConnectAddress": "修改连接地址",
    "Settings-Stage1": "修改刷关关卡",
    "CaptureImage": "截图（排队）",
    "CaptureImageNow": "截图（立即）",
    "StopTask": "停止当前任务",
    "HeartBeat": "心跳",
}


def format_datetime(value: datetime | None) -> str:
    if value is None:
        return "—"
    # 数据库里存的是「不带时区的 UTC」
    aware = value.replace(tzinfo=timezone.utc).astimezone()
    return aware.strftime("%Y-%m-%d %H:%M:%S")


def time_ago(value: datetime | None) -> str:
    if value is None:
        return "从未"
    aware = value.replace(tzinfo=timezone.utc)
    seconds = int((datetime.now(timezone.utc) - aware).total_seconds())
    if seconds < 5:
        return "刚刚"
    if seconds < 60:
        return f"{seconds} 秒前"
    if seconds < 3600:
        return f"{seconds // 60} 分钟前"
    if seconds < 86400:
        return f"{seconds // 3600} 小时前"
    return f"{seconds // 86400} 天前"


templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
templates.env.filters["fmt_datetime"] = format_datetime
templates.env.filters["time_ago"] = time_ago
templates.env.globals.update(
    app_name="MAA 远程控制",
    app_version=__version__,
    status_labels=STATUS_LABELS,
    task_labels=TASK_LABELS,
    public_base_url=settings.public_base_url,
    allow_registration=settings.allow_registration,
)
