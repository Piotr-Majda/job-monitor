import asyncio
import html
from datetime import timedelta

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import settings
from .db import Delivery, Job, Match, Profile, Run, engine, now, task_lock
from .matching import assess
from .source import collect


def upsert_job(data, db=engine):
    with Session(db) as session:
        job = session.scalar(select(Job).where(Job.source_id == data["source_id"]))
        if job is None:
            job = Job(**data)
            session.add(job)
        else:
            for key, value in data.items():
                setattr(job, key, value)
            job.last_seen = now()
        session.flush()
        new_matches = 0
        for profile in session.scalars(select(Profile).where(Profile.enabled.is_(True))):
            result = assess(job, profile.criteria)
            match = session.scalar(select(Match).where(Match.profile_id == profile.id, Match.job_id == job.id))
            if match is None:
                match = Match(profile_id=profile.id, job_id=job.id, eligible=result["eligible"], assessment=result)
                session.add(match)
                new_matches += int(result["eligible"])
            else:
                if result["eligible"] and not match.eligible:
                    match.discovered_at = now()
                    new_matches += 1
                match.eligible, match.assessment = result["eligible"], result
        session.commit()
        return new_matches


def reassess_profile(profile_id, db=engine):
    with Session(db) as session:
        profile = session.get(Profile, profile_id)
        for job in session.scalars(select(Job)):
            result = assess(job, profile.criteria)
            match = session.scalar(select(Match).where(Match.profile_id == profile_id, Match.job_id == job.id))
            if not match:
                session.add(Match(profile_id=profile_id, job_id=job.id, eligible=result["eligible"], assessment=result))
            else:
                match.eligible, match.assessment = result["eligible"], result
        session.commit()


async def run_collection(config=settings, db=engine):
    with task_lock("collection", db) as acquired:
        if not acquired:
            return {"status": "busy"}
        with Session(db) as session:
            # A terminated process may leave a visible run without a final state.
            for old in session.scalars(select(Run).where(Run.status == "running")):
                old.status, old.finished_at = "failed", now()
                old.errors = ["Previous collection was interrupted before completion"]
            run = Run(coverage=f"Public Testing category; at most {config.max_pages} pages / {config.max_jobs} listings. Not exhaustive.")
            session.add(run)
            session.commit()
            run_id = run.id
        count = 0

        def save(data):
            nonlocal count
            count += upsert_job(data, db)

        try:
            fetched, errors, attempted = await asyncio.wait_for(collect(config, save), timeout=25 * 60)
            status = "partial" if fetched and errors else "failed" if errors else "success"
        except Exception as error:
            # Do not put environment values, HTTP headers, or secrets into logs.
            fetched = 0
            with Session(db) as session:
                started = session.get(Run, run_id).started_at
                fetched = len(list(session.scalars(select(Job.id).where(Job.last_seen >= started))))
            errors, attempted, status = [f"Collection stopped ({type(error).__name__}). Check source access and worker logs."], 0, "failed"
        with Session(db) as session:
            run = session.get(Run, run_id)
            run.status, run.fetched, run.new_matches = status, fetched, count
            run.errors, run.finished_at = errors, now()
            run.coverage += f" Retrieved {fetched} descriptions; examined {attempted} distinct links."
            session.commit()
        return {"status": status, "fetched": fetched, "new_matches": count, "errors": errors}


def digest_content(rows, config=settings):
    escape = html.escape
    subject = f"Your QA inbox: {len(rows)} new job match{'es' if len(rows) != 1 else ''}"
    parts = ["<h1>Your next opportunity</h1><p>New matches from Just Join IT. These are recommendations for your review, not applications.</p>"]
    for match, job, profile in rows:
        reasons = "<br>".join(escape(x) for x in match.assessment["reasons"])
        parts.append(f'<h2><a href="{escape(job.url, quote=True)}">{escape(job.title)}</a></h2><p>{escape(job.company)} · {escape(profile.name)}</p><p>{reasons}</p>')
    parts.append(f'<p><a href="{escape(config.app_url, quote=True)}">Open your dashboard</a></p><p>First discovered by this monitor; not necessarily newly posted.</p>')
    return subject, "\n".join(parts)


async def send_digest(config=settings, db=engine, transport=None):
    if not config.email_ready:
        return {"status": "not_configured", "message": "Configure EMAIL_TO, EMAIL_FROM and RESEND_API_KEY"}
    with task_lock("digest", db) as acquired:
        if not acquired:
            return {"status": "busy"}
        with Session(db) as session:
            # Wait for a consistent completed collection; try again on the next
            # worker tick, even if today's digest time has already passed.
            running = session.scalar(select(Run).where(Run.status == "running", Run.started_at > now() - timedelta(minutes=30)))
            if running:
                return {"status": "collection_running"}
            delivery = session.scalar(select(Delivery).where(Delivery.status.in_(["pending", "failed"])).order_by(Delivery.created_at))
            if delivery and now() - delivery.created_at > timedelta(hours=23):
                delivery.status = "needs_review"
                delivery.error = "Provider idempotency window nearly expired; verify delivery with provider before retrying manually."
                session.commit()
                return {"status": "needs_review"}
            if session.scalar(select(Delivery).where(Delivery.status == "needs_review")):
                return {"status": "needs_review"}
            if delivery is None:
                rows = list(session.execute(select(Match, Job, Profile).join(Job, Match.job_id == Job.id).join(Profile, Match.profile_id == Profile.id).where(
                    Match.eligible.is_(True), Match.notified_at.is_(None),
                    Match.status.in_(["new", "saved"]), Profile.enabled.is_(True),
                ).order_by(Match.discovered_at)))
                # Re-check expiry as jobs may have closed since the last scan.
                rows = [row for row in rows if assess(row[1], row[2].criteria)["eligible"]]
                if not rows:
                    return {"status": "empty"}
                subject, body = digest_content(rows, config)
                delivery = Delivery(match_ids=[row[0].id for row in rows], recipient=config.email_to, subject=subject, body=body)
                session.add(delivery)
                session.commit()
            delivery_id, recipient, subject, body = delivery.id, delivery.recipient, delivery.subject, delivery.body
        try:
            async with httpx.AsyncClient(timeout=30, transport=transport) as client:
                response = await client.post("https://api.resend.com/emails", headers={
                    "Authorization": f"Bearer {config.resend_api_key}", "Idempotency-Key": delivery_id,
                }, json={"from": config.email_from, "to": [recipient], "subject": subject, "html": body})
                response.raise_for_status()
                provider_id = response.json()["id"]
        except Exception as error:
            with Session(db) as session:
                delivery = session.get(Delivery, delivery_id)
                delivery.status, delivery.error = "failed", f"Email delivery failed ({type(error).__name__}); pending for retry"
                session.commit()
            return {"status": "failed"}
        with Session(db) as session:
            delivery = session.get(Delivery, delivery_id)
            delivery.status, delivery.provider_id, delivery.error, delivery.sent_at = "sent", provider_id, None, now()
            for match in session.scalars(select(Match).where(Match.id.in_(delivery.match_ids))):
                match.notified_at = now()
            session.commit()
        return {"status": "sent", "delivery_id": delivery_id}
