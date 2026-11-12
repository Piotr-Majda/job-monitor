"""Run exactly one worker service; database leases also protect manual runs."""
import asyncio
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import settings
from .db import Delivery, Run, engine, init_db
from .services import run_collection, send_digest

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


async def tick():
    local = datetime.now(ZoneInfo(settings.timezone))
    current = (local.hour, local.minute)
    search_due = tuple(map(int, settings.search_time.split(":")))
    digest_due = tuple(map(int, settings.digest_time.split(":")))
    with Session(engine) as session:
        latest = session.scalar(select(Run).order_by(Run.started_at.desc()).limit(1))
        ran_today = bool(latest and latest.started_at.replace(tzinfo=ZoneInfo("UTC")).astimezone(ZoneInfo(settings.timezone)).date() == local.date())
        sent = session.scalar(select(Delivery).where(Delivery.status == "sent").order_by(Delivery.sent_at.desc()).limit(1))
        sent_today = bool(sent and sent.sent_at and sent.sent_at.replace(tzinfo=ZoneInfo("UTC")).astimezone(ZoneInfo(settings.timezone)).date() == local.date())
    if current >= search_due and not ran_today:
        result = await run_collection()
        logging.info("Collection: %s", result)
        if result["status"] in ("failed", "partial"):
            raise RuntimeError("Collection incomplete; inspect collection health on the dashboard")
    if current >= digest_due and not sent_today:
        result = await send_digest()
        if result["status"] not in ("empty", "not_configured"):
            logging.info("Digest: %s", result["status"])
        if result["status"] in ("failed", "needs_review"):
            raise RuntimeError("Email delivery needs attention; inspect dashboard delivery history")


async def main():
    settings.validate()
    init_db()
    scheduler = AsyncIOScheduler(timezone=settings.timezone)
    scheduler.add_job(tick, "interval", minutes=5, max_instances=1, coalesce=True)
    scheduler.start()
    try:
        await tick()  # Catch up after startup; never depends on a browser tab being open.
        await asyncio.Event().wait()
    finally:
        scheduler.shutdown(wait=False)


if __name__ == "__main__":
    asyncio.run(main())
