import asyncio
from datetime import timedelta

import httpx
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import Settings
from app.db import Delivery, Job, Match, Profile, now, task_lock
from app.services import reassess_profile, send_digest, upsert_job


def email_settings():
    return Settings(email_to="owner@example.test", email_from="Scout <sender@example.test>", resend_api_key="test-key")


def test_rescan_preserves_status_notification_and_first_seen(db, job_data):
    assert upsert_job(job_data, db) == 1
    with Session(db) as session:
        match = session.scalar(select(Match))
        match.status, match.notified_at = "dismissed", now()
        first_seen = session.scalar(select(Job)).first_seen
        session.commit()
    job_data["description"] += " Updated requirements."
    assert upsert_job(job_data, db) == 0
    with Session(db) as session:
        assert session.scalar(select(func.count(Job.id))) == 1
        assert session.scalar(select(Job)).first_seen == first_seen
        match = session.scalar(select(Match))
        assert match.status == "dismissed" and match.notified_at is not None


def test_profiles_have_independent_matching(db, job_data):
    upsert_job(job_data, db)
    with Session(db) as session:
        profile = Profile(name="Java QA", criteria={"skills": ["Java"], "levels": ["mid"]})
        session.add(profile)
        session.commit()
        profile_id = profile.id
    reassess_profile(profile_id, db)
    with Session(db) as session:
        assert session.scalar(select(Match).where(Match.profile_id == 1)).eligible
        assert not session.scalar(select(Match).where(Match.profile_id == profile_id)).eligible


def test_database_lease_prevents_overlapping_work(db):
    with task_lock("collection", db) as first:
        assert first
        with task_lock("collection", db) as second:
            assert not second
    with task_lock("collection", db) as third:
        assert third


def test_failed_delivery_reuses_outbox_id_then_marks_notified(db, job_data):
    upsert_job(job_data, db)
    keys = []
    def provider(request):
        keys.append(request.headers["idempotency-key"])
        return httpx.Response(503 if len(keys) == 1 else 200, json={"id": "provider-id"})
    transport = httpx.MockTransport(provider)
    config = email_settings()
    assert asyncio.run(send_digest(config, db, transport))["status"] == "failed"
    with Session(db) as session:
        assert session.scalar(select(Match)).notified_at is None
    assert asyncio.run(send_digest(config, db, transport))["status"] == "sent"
    assert len(keys) == 2 and keys[0] == keys[1]
    assert asyncio.run(send_digest(config, db, transport))["status"] == "empty"
    with Session(db) as session:
        assert session.scalar(select(Match)).notified_at is not None
        assert session.scalar(select(Delivery)).sent_at is not None


def test_dismissed_matches_do_not_generate_email(db, job_data):
    upsert_job(job_data, db)
    with Session(db) as session:
        session.scalar(select(Match)).status = "dismissed"
        session.commit()
    assert asyncio.run(send_digest(email_settings(), db))["status"] == "empty"


def test_expired_idempotency_window_requires_review(db):
    with Session(db) as session:
        session.add(Delivery(created_at=now() - timedelta(hours=24), match_ids=[], recipient="owner@example.test", subject="Test", body="Test", status="failed"))
        session.commit()
    assert asyncio.run(send_digest(email_settings(), db))["status"] == "needs_review"


def test_missing_email_configuration_does_not_mark_anything_notified(db, job_data):
    upsert_job(job_data, db)
    assert asyncio.run(send_digest(Settings(email_to="", email_from="", resend_api_key=""), db))["status"] == "not_configured"
    with Session(db) as session:
        assert session.scalar(select(Match)).notified_at is None
