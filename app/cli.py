import argparse
import asyncio
import json
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import settings
from .db import Job, Match, Profile, engine, init_db
from .services import digest_content, run_collection, send_digest


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["init", "collect", "digest", "preview-email"])
    args = parser.parse_args()
    settings.validate()
    init_db()
    if args.command == "collect":
        print(json.dumps(asyncio.run(run_collection()), indent=2))
    elif args.command == "digest":
        print(json.dumps(asyncio.run(send_digest()), indent=2))
    elif args.command == "preview-email":
        with Session(engine) as session:
            rows = list(session.execute(select(Match, Job, Profile).join(Job, Match.job_id == Job.id).join(Profile, Match.profile_id == Profile.id).where(Match.eligible.is_(True), Match.status.in_(["new", "saved"]))))
            subject, body = digest_content(rows)
        target = Path("data/digest-preview.html")
        target.write_text(body)
        print(f"{subject}\nPreview saved: {target.resolve()} (no email sent)")


if __name__ == "__main__":
    main()
