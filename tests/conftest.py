"""pytest 公共配置：在导入应用之前把环境变量指向临时目录。"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

import pytest

# 放在项目内的临时目录：Windows 下 TMP=/tmp 这种 POSIX 路径会让 tempfile 回退到当前目录
_TMP = Path(__file__).resolve().parents[1] / ".pytest-tmp"
_TMP.mkdir(parents=True, exist_ok=True)

os.environ["MAA_REMOTE_DATA_DIR"] = str(_TMP)
os.environ["MAA_REMOTE_DATABASE_URL"] = f"sqlite:///{(_TMP / 'test.db').as_posix()}"
os.environ["MAA_REMOTE_SECRET_KEY"] = "test-secret-key"
os.environ["MAA_REMOTE_PUBLIC_BASE_URL"] = "http://testserver"
os.environ["MAA_REMOTE_ALLOW_REGISTRATION"] = "true"


@pytest.fixture()
def client():
    from fastapi.testclient import TestClient

    from maa_remote.config import settings
    from maa_remote.db import Base, engine
    from maa_remote.main import create_app

    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    shutil.rmtree(settings.screenshot_dir, ignore_errors=True)
    settings.screenshot_dir.mkdir(parents=True, exist_ok=True)

    app = create_app()
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture()
def db_session():
    from maa_remote.db import SessionLocal

    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
