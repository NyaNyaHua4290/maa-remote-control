"""截图解码与落盘。

MAA 的截图任务会把整张图以 Base64 字符串放进 reportStatus 的 payload 里，
可能是裸 Base64，也可能是 `data:image/png;base64,...` 形式的 Data URL。
"""

from __future__ import annotations

import base64
import binascii
import re
from pathlib import Path

from ..config import settings

# 允许的图片后缀，防止被写入奇怪的文件名
_ALLOWED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}
_DATA_URL_PATTERN = re.compile(r"^data:image/(?P<fmt>[a-zA-Z0-9.+-]+);base64,", re.IGNORECASE)

# 单张截图上限，防止磁盘被撑爆
MAX_SCREENSHOT_BYTES = 32 * 1024 * 1024


class ScreenshotError(ValueError):
    """截图内容无法解析。"""


def _extension_from_mime(fmt: str) -> str:
    fmt = fmt.lower()
    if fmt in {"jpeg", "jpg"}:
        return ".jpg"
    if fmt in {"png", "webp", "bmp"}:
        return f".{fmt}"
    return ".png"


def decode_screenshot(payload: str) -> tuple[bytes, str]:
    """把 payload 解析成 (二进制内容, 文件后缀)。"""

    if not payload:
        raise ScreenshotError("截图 payload 为空")

    raw = payload.strip()
    extension = ".png"

    match = _DATA_URL_PATTERN.match(raw)
    if match:
        extension = _extension_from_mime(match.group("fmt"))
        raw = raw[match.end():]

    # 去掉可能的换行和空白
    raw = "".join(raw.split())

    try:
        blob = base64.b64decode(raw, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ScreenshotError("截图 payload 不是合法的 Base64") from exc

    if not blob:
        raise ScreenshotError("截图内容为空")
    if len(blob) > MAX_SCREENSHOT_BYTES:
        raise ScreenshotError(f"截图超过 {MAX_SCREENSHOT_BYTES // 1024 // 1024} MiB 上限")
    if extension not in _ALLOWED_EXTENSIONS:
        extension = ".png"

    return blob, extension


def save_screenshot(task_id: str, payload: str) -> tuple[str, int]:
    """保存截图，返回 (文件名, 字节数)。"""

    blob, extension = decode_screenshot(payload)
    filename = f"{task_id}{extension}"
    path: Path = settings.screenshot_dir / filename
    path.write_bytes(blob)
    return filename, len(blob)


def screenshot_path(filename: str) -> Path:
    """把数据库里记录的文件名还原成绝对路径（并做一次目录穿越校验）。"""

    candidate = (settings.screenshot_dir / filename).resolve()
    if not str(candidate).startswith(str(settings.screenshot_dir.resolve())):
        raise ScreenshotError("非法的截图文件名")
    return candidate


def delete_screenshot(filename: str | None) -> None:
    if not filename:
        return
    try:
        screenshot_path(filename).unlink(missing_ok=True)
    except ScreenshotError:  # pragma: no cover - 非法文件名直接忽略
        return
