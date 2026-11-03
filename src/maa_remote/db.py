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
    """建表（幂等）。小项目不引入 Alembic，表结构变化时自行迁移。"""

    from . import models  # noqa: F401  # 保证模型注册到 metadata

    Base.metadata.create_all(bind=engine)
    logger.info("数据库已就绪：%s", settings.database_url)
