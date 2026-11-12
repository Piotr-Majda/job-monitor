from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import NullPool

from app import scheduled, web
from app.config import Settings
from app.db import make_engine


def test_free_hosting_cannot_persist_to_ephemeral_sqlite():
    with pytest.raises(ValueError, match="external PostgreSQL"):
        Settings(deployment_mode="free", database_url="sqlite:///temporary.db").validate()


def test_scheduled_job_does_not_need_dashboard_cookie_or_password():
    config = Settings(deployment_mode="free", production=True,
                      database_url="postgresql://example:example@localhost/db?sslmode=require",
                      app_url="https://example.onrender.com", admin_password="", session_secret="")
    config.validate(require_web_security=False)
    with pytest.raises(ValueError, match="ADMIN_PASSWORD"):
        config.validate()


def test_free_database_connections_are_not_kept_in_idle_pool(monkeypatch):
    from app import db
    monkeypatch.setattr(db.settings, "deployment_mode", "free")
    engine = make_engine("postgres://example:example@localhost/db")
    try:
        assert isinstance(engine.pool, NullPool)
        assert engine.url.drivername == "postgresql+psycopg"
    finally:
        engine.dispose()


def test_platform_probes_do_not_wake_serverless_database(monkeypatch):
    monkeypatch.setattr(web, "init_db", lambda: None)
    monkeypatch.setattr(web.settings, "admin_password", "a-long-private-password")
    class ForbiddenSession:
        def __init__(self, *_args, **_kwargs):
            raise AssertionError("Health probes must not connect to PostgreSQL")
    monkeypatch.setattr(web, "Session", ForbiddenSession)
    with TestClient(web.app) as client:
        for _ in range(3):
            assert client.get("/health").json()["status"] == "ok"
        assert client.get("/database-health").status_code == 401


def test_one_shot_scheduler_exits_and_sanitizes_connection_errors(monkeypatch, caplog):
    sentinel = "postgresql://private-user:private-password@example/db"
    def broken_init():
        raise RuntimeError(sentinel)
    monkeypatch.setattr(scheduled.settings, "validate", lambda **kwargs: None)
    monkeypatch.setattr(scheduled, "init_db", broken_init)
    assert scheduled.main() == 1
    assert sentinel not in caplog.text
    assert "RuntimeError" in caplog.text


def test_one_shot_scheduler_executes_due_check_once(monkeypatch):
    calls = []
    monkeypatch.setattr(scheduled.settings, "validate", lambda **kwargs: None)
    monkeypatch.setattr(scheduled, "init_db", lambda: calls.append("init"))
    async def due_check():
        calls.append("tick")
    monkeypatch.setattr(scheduled, "tick", due_check)
    assert scheduled.main() == 0
    assert calls == ["init", "tick"]
