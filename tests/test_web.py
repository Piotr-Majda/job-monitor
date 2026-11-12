import re

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import web
from app.config import Settings
from app.db import Match, init_db
from app.services import upsert_job


def test_dashboard_real_data_actions_csrf_and_escaping(db, job_data, monkeypatch):
    job_data["company"] = '<script>alert("x")</script>'
    upsert_job(job_data, db)
    monkeypatch.setattr(web, "engine", db)
    monkeypatch.setattr(web, "init_db", lambda: init_db(db))
    monkeypatch.setattr(web.settings, "admin_password", "")
    with TestClient(web.app) as client:
        page = client.get("/")
        assert page.status_code == 200
        assert "&lt;script&gt;" in page.text
        assert '<script>alert("x")</script>' not in page.text
        csrf = re.search('name="csrf" value="([^"]+)"', page.text).group(1)
        with Session(db) as session:
            match_id = session.scalar(select(Match.id))
        assert client.post(f"/matches/{match_id}/status", data={"status": "saved", "csrf": "bad"}).status_code == 403
        assert client.post(f"/matches/{match_id}/status", data={"status": "saved", "csrf": csrf}).status_code == 200
        assert "Saved opportunities" in client.get("/?view=saved").text
    with Session(db) as session:
        assert session.get(Match, match_id).status == "saved"


def test_private_dashboard_requires_login(db, monkeypatch):
    monkeypatch.setattr(web, "engine", db)
    monkeypatch.setattr(web, "init_db", lambda: init_db(db))
    monkeypatch.setattr(web.settings, "admin_password", "a-long-private-password")
    with TestClient(web.app) as client:
        assert client.get("/", follow_redirects=False).status_code == 303
        assert client.get("/health").status_code == 200
        page = client.get("/login")
        csrf = re.search('name="csrf" value="([^"]+)"', page.text).group(1)
        assert client.post("/login", data={"password": "a-long-private-password", "csrf": csrf}).status_code == 200
        assert client.get("/").status_code == 200


def test_production_requires_auth_and_https():
    import pytest
    with pytest.raises(ValueError):
        Settings(production=True, admin_password="", session_secret="").validate()
    with pytest.raises(ValueError):
        Settings(production=True, admin_password="a" * 20, session_secret="b" * 40, app_url="http://example.test").validate()
