import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import web
from app.db import Base, Job, Match, Profile, make_engine, now
from app.migrate import copy_database, receipts
from app.services import upsert_job


def test_migration_preserves_reviews_and_notifications_and_never_reimports(db, job_data, tmp_path):
    upsert_job(job_data, db)
    with Session(db) as session:
        match = session.scalar(select(Match))
        match.status, match.notified_at = "saved", now()
        session.commit()
    target = make_engine(f"sqlite:///{tmp_path}/target.db")
    result = copy_database(db, target)
    assert result["status"] == "completed"
    assert result["counts"]["jobs"] == result["counts"]["matches"] == 1
    with Session(target) as session:
        match = session.scalar(select(Match))
        assert match.status == "saved" and match.notified_at is not None
        match.status = "applied"
        session.commit()
    assert copy_database(db, target)["status"] == "already_completed"
    with Session(target) as session:
        assert session.scalar(select(Match)).status == "applied"
    with target.connect() as connection:
        receipt = connection.execute(select(receipts)).mappings().one()
        assert receipt["snapshot"]["matches"][0]["status"] == "saved"
    target.dispose()


def test_migration_refuses_nonempty_destination(db, tmp_path):
    from app.db import init_db
    target = make_engine(f"sqlite:///{tmp_path}/target.db")
    init_db(target)
    with pytest.raises(RuntimeError, match="refusing to overwrite"):
        copy_database(db, target)
    with Session(target) as session:
        assert session.scalar(select(Profile)).name == "QA · Python · Poland"
    target.dispose()


def test_migration_read_only_mode_blocks_reviews_but_allows_login_page(db, monkeypatch):
    from app.db import init_db
    monkeypatch.setattr(web, "engine", db)
    monkeypatch.setattr(web, "init_db", lambda: init_db(db))
    monkeypatch.setattr(web.settings, "migration_read_only", True)
    with TestClient(web.app) as client:
        assert client.get("/login").status_code == 200
        assert client.get("/health").json()["migration_read_only"]
        assert client.post("/profiles", data={}).status_code == 503
