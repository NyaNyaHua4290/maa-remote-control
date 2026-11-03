"""运行时配置：既支持 Docker 用环境变量注入，也支持 Windows 直接双击 exe 运行。"""

from __future__ import annotations

import os
import secrets
import sys
from dataclasses import dataclass
from pathlib import Path

# 项目根目录（src/maa_remote/config.py -> 上三级）
PROJECT_ROOT = Path(__file__).resolve().parents[2]

# 没有配置密钥、且数据目录不可写时使用的兜底值，生产环境会给出告警
DEV_SECRET = "dev-only-insecure-secret-change-me"


def app_root() -> Path:
    """应用根目录：打包成 exe 后是 exe 所在目录，否则是项目根目录。"""

    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return PROJECT_ROOT


def _resolve_secret(data_dir: Path) -> str:
    """优先读环境变量；没有就在数据目录里生成并持久化一个随机密钥。"""

    env_secret = os.getenv("MAA_REMOTE_SECRET_KEY")
    if env_secret:
        return env_secret

    secret_file = data_dir / "secret.key"
    try:
        if secret_file.exists():
            existing = secret_file.read_text(encoding="utf-8").strip()
            if existing:
                return existing
        generated = secrets.token_urlsafe(48)
        secret_file.write_text(generated, encoding="utf-8")
        return generated
    except OSError:
        # 目录只读（比如装进了 Program Files）时退回开发密钥，由启动日志告警
        return DEV_SECRET

# MAA 默认 1 秒轮询一次，留出余量后 30 秒没请求就视为离线
ONLINE_THRESHOLD_SECONDS = 30

# 任务下发后多久没有回报就判定为超时（MAA 崩溃/断网时任务不会永远卡住）
TASK_TIMEOUT_MINUTES = 15

# 允许下发的任务类型，详见 MAA 官方远程控制协议
SUPPORTED_TASK_TYPES: tuple[str, ...] = (
    "LinkStart",
    "LinkStart-Base",
    "LinkStart-WakeUp",
    "LinkStart-Combat",
    "LinkStart-Recruiting",
    "LinkStart-Mall",
    "LinkStart-Mission",
    "LinkStart-AutoRoguelike",
    "Toolbox-GachaOnce",
    "Toolbox-GachaTenTimes",
    "Toolbox-Reclamation",
    "Settings-ConnectAddress",
    "Settings-Stage1",
    "CaptureImage",
    "CaptureImageNow",
    "StopTask",
    "HeartBeat",
)


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    return raw.strip().lower() in {"1", "true", "yes", "y", "on"}


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw)
    except ValueError as exc:  # pragma: no cover - 配置错误时直接暴露
        raise ValueError(f"环境变量 {name} 必须是整数，当前值：{raw!r}") from exc


@dataclass(frozen=True)
class Settings:
    """应用配置快照。"""

    secret_key: str
    database_url: str
    data_dir: Path
    public_base_url: str
    allow_registration: bool
    session_max_age: int
    max_payload_bytes: int
    log_level: str
    cookie_secure: bool

    @property
    def screenshot_dir(self) -> Path:
        return self.data_dir / "screenshots"

    @property
    def using_default_secret(self) -> bool:
        return self.secret_key == DEV_SECRET


def load_settings() -> Settings:
    data_dir = Path(
        os.getenv("MAA_REMOTE_DATA_DIR") or (app_root() / "data")
    ).expanduser()
    data_dir = data_dir.resolve()
    data_dir.mkdir(parents=True, exist_ok=True)

    database_url = os.getenv("MAA_REMOTE_DATABASE_URL") or f"sqlite:///{(data_dir / 'maa-remote.db').as_posix()}"

    public_base_url = (os.getenv("MAA_REMOTE_PUBLIC_BASE_URL") or "http://127.0.0.1:8000").rstrip("/")

    settings = Settings(
        secret_key=_resolve_secret(data_dir),
        database_url=database_url,
        data_dir=data_dir,
        public_base_url=public_base_url,
        allow_registration=_env_bool("MAA_REMOTE_ALLOW_REGISTRATION", True),
        session_max_age=_env_int("MAA_REMOTE_SESSION_MAX_AGE", 60 * 60 * 24 * 14),
        max_payload_bytes=_env_int("MAA_REMOTE_MAX_PAYLOAD_MB", 64) * 1024 * 1024,
        log_level=(os.getenv("MAA_REMOTE_LOG_LEVEL") or "INFO").upper(),
        cookie_secure=public_base_url.startswith("https://"),
    )
    settings.screenshot_dir.mkdir(parents=True, exist_ok=True)
    return settings


settings = load_settings()


def generate_user_key() -> str:
    """生成给 MAA「用户标识符」用的随机密钥。"""

    return secrets.token_urlsafe(24)
