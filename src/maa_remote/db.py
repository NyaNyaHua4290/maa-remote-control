"""数据库引擎与会话管理。"""

from __future__ import annotations

import logging
from collections.abc import Iterator

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import settings

logger = logging.getLogger(__name__)


class Base(DeclarativeBase):
    """所有 ORM 模型的基类。"""


def _engine_options(url: str) -> dict:
    if url.startswith("sqlite"):
        # SQLite 在多线程（uvicorn 线程池）下需要关闭 check_same_thread
        return {"connect_args": {"check_same_thread": False, "timeout": 15}}
    return {"pool_pre_ping": True}


engine = create_engine(settings.database_url, future=True, **_engine_options(settings.database_url))

if settings.database_url.startswith("sqlite"):

    @event.listens_for(engine, "connect")
    def _set_sqlite_pragma(dbapi_connection, _connection_record) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, class_=Session)


def get_db() -> Iterator[Session]:
    """FastAPI 依赖：每个请求一个会话。"""

    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """建表（幂等）并做一点轻量迁移。小项目不引入 Alembic。"""

    from . import models  # noqa: F401  # 保证模型注册到 metadata

    Base.metadata.create_all(bind=engine)
    _migrate()
    _ensure_admin_exists()
    logger.info("数据库已就绪：%s", settings.database_url)


def _migrate() -> None:
    """给老数据库补上后加的列（create_all 不会改已存在的表）。"""

    from sqlalchemy import inspect, text

    inspector = inspect(engine)
    if "users" not in inspector.get_table_names():
        return

    columns = {column["name"] for column in inspector.get_columns("users")}
    if "is_admin" not in columns:
        with engine.begin() as connection:
            connection.execute(text("ALTER TABLE users ADD COLUMN is_admin BOOLEAN NOT NULL DEFAULT 0"))
        logger.info("已为 users 表补充 is_admin 列")


def _ensure_admin_exists() -> None:
    """老部署里可能一个管理员都没有，把最早注册的账号提升为管理员。"""

    from sqlalchemy import func, select

    from .models import User

    with SessionLocal() as db:
        user_count = db.scalar(select(func.count()).select_from(User)) or 0
        if user_count == 0:
            return

        admin_count = db.scalar(select(func.count()).select_from(User).where(User.is_admin.is_(True))) or 0
        if admin_count:
            return

        first_user = db.scalar(select(User).order_by(User.id).limit(1))
        if first_user is not None:
            first_user.is_admin = True
            db.commit()
            logger.warning("检测到没有管理员，已把最早注册的账号 %s 提升为管理员", first_user.username)
