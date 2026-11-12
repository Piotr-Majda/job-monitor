import asyncio
from datetime import datetime as RealDateTime, timezone

from sqlalchemy.orm import Session

from app import worker
from app.db import Delivery, Run


def test_worker_uses_warsaw_day_and_does_not_repeat_sent_digest(db, monkeypatch):
    # On the DST start date 05:05 UTC is 07:05 in Warsaw, not 06:05.
    instant = RealDateTime(2026, 3, 29, 5, 5, tzinfo=timezone.utc)
    class Clock(RealDateTime):
        @classmethod
        def now(cls, tz=None):
            return instant.astimezone(tz) if tz else instant.replace(tzinfo=None)
    monkeypatch.setattr(worker, "datetime", Clock)
    monkeypatch.setattr(worker, "engine", db)
    calls = []
    async def collect():
        calls.append("collect")
        with Session(db) as session:
            session.add(Run(started_at=instant.replace(tzinfo=None), status="success"))
            session.commit()
        return {"status": "success"}
    async def digest():
        calls.append("digest")
        with Session(db) as session:
            session.add(Delivery(created_at=instant.replace(tzinfo=None), sent_at=instant.replace(tzinfo=None), status="sent", recipient="test@example.test", subject="Test", body="Test", match_ids=[]))
            session.commit()
        return {"status": "sent"}
    monkeypatch.setattr(worker, "run_collection", collect)
    monkeypatch.setattr(worker, "send_digest", digest)
    asyncio.run(worker.tick())
    asyncio.run(worker.tick())
    assert calls == ["collect", "digest"]


def test_worker_does_not_search_before_warsaw_morning(db, monkeypatch):
    # During winter 04:30 UTC is 05:30 Warsaw, still before the search.
    instant = RealDateTime(2026, 11, 12, 4, 30, tzinfo=timezone.utc)
    class Clock(RealDateTime):
        @classmethod
        def now(cls, tz=None):
            return instant.astimezone(tz)
    monkeypatch.setattr(worker, "datetime", Clock)
    monkeypatch.setattr(worker, "engine", db)
    async def unexpected():
        raise AssertionError("Task ran before its schedule")
    monkeypatch.setattr(worker, "run_collection", unexpected)
    monkeypatch.setattr(worker, "send_digest", unexpected)
    asyncio.run(worker.tick())
