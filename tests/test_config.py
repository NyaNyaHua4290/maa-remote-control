"""配置相关的测试：密钥自动生成与持久化、数据目录解析。"""

from __future__ import annotations

from maa_remote import config


def test_secret_is_generated_and_reused(tmp_path, monkeypatch):
    monkeypatch.delenv("MAA_REMOTE_SECRET_KEY", raising=False)

    first = config._resolve_secret(tmp_path)
    second = config._resolve_secret(tmp_path)

    assert first == second
    assert len(first) >= 32
    assert (tmp_path / "secret.key").read_text(encoding="utf-8").strip() == first


def test_secret_env_wins(tmp_path, monkeypatch):
    monkeypatch.setenv("MAA_REMOTE_SECRET_KEY", "from-env")

    assert config._resolve_secret(tmp_path) == "from-env"
    assert not (tmp_path / "secret.key").exists()


def test_app_root_points_to_project_outside_pyinstaller():
    assert config.app_root() == config.PROJECT_ROOT
