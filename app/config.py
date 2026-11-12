import os
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


@dataclass
class Settings:
    database_url: str = field(default_factory=lambda: os.getenv("DATABASE_URL", f"sqlite:///{ROOT}/data/jobs.db"))
    app_url: str = field(default_factory=lambda: (os.getenv("APP_URL") or os.getenv("RENDER_EXTERNAL_URL") or "http://localhost:8000").rstrip("/"))
    admin_password: str = field(default_factory=lambda: os.getenv("ADMIN_PASSWORD", ""))
    session_secret: str = field(default_factory=lambda: os.getenv("SESSION_SECRET", ""))
    production: bool = field(default_factory=lambda: os.getenv("ENVIRONMENT") == "production")
    timezone: str = "Europe/Warsaw"
    search_time: str = field(default_factory=lambda: os.getenv("SEARCH_TIME", "06:00"))
    digest_time: str = field(default_factory=lambda: os.getenv("DIGEST_TIME", "07:00"))
    max_pages: int = field(default_factory=lambda: int(os.getenv("MAX_PAGES", "3")))
    max_jobs: int = field(default_factory=lambda: int(os.getenv("MAX_JOBS", "150")))
    request_delay: float = field(default_factory=lambda: float(os.getenv("REQUEST_DELAY", "1.5")))
    email_to: str = field(default_factory=lambda: os.getenv("EMAIL_TO", ""))
    email_from: str = field(default_factory=lambda: os.getenv("EMAIL_FROM", ""))
    resend_api_key: str = field(default_factory=lambda: os.getenv("RESEND_API_KEY", ""))

    @property
    def email_ready(self):
        return bool(self.email_to and self.email_from and self.resend_api_key)

    def validate(self):
        for value in (self.search_time, self.digest_time):
            hour, minute = map(int, value.split(":"))
            if not (0 <= hour <= 23 and 0 <= minute <= 59):
                raise ValueError("Schedules must use HH:MM")
        if not (1 <= self.max_pages <= 20 and 1 <= self.max_jobs <= 1000 and self.request_delay >= 1):
            raise ValueError("Invalid collection limits; delay must be at least one second")
        if self.production:
            if len(self.admin_password) < 16 or len(self.session_secret) < 32:
                raise ValueError("Production requires ADMIN_PASSWORD (16+ characters) and SESSION_SECRET (32+)")
            if not self.app_url.startswith("https://"):
                raise ValueError("Production requires an HTTPS APP_URL")


settings = Settings()
