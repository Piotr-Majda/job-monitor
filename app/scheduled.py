"""One due-work check for GitHub Actions; exits instead of staying online."""
import asyncio
import logging

from .config import settings
from .db import init_db
from .worker import tick


def main():
    try:
        # No HTTP surface: dashboard passwords/cookie secrets stay out of Actions.
        settings.validate(require_web_security=False)
        init_db()
        asyncio.run(tick())
    except Exception as error:
        # Do not expose connection strings or provider keys in public logs.
        logging.error("Scheduled check failed (%s). Inspect dashboard health and repository secret configuration.", type(error).__name__)
        return 1
    logging.info("Scheduled check complete; due work processed or already done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
