from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, JSON, String, Text, UniqueConstraint, create_engine, select, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

from .config import settings


def now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Base(DeclarativeBase):
    pass


class Profile(Base):
    __tablename__ = "profiles"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    criteria: Mapped[dict] = mapped_column(JSON)


class Job(Base):
    __tablename__ = "jobs"
    id: Mapped[int] = mapped_column(primary_key=True)
    source_id: Mapped[str] = mapped_column(String(500), unique=True)
    url: Mapped[str] = mapped_column(Text)
    title: Mapped[str] = mapped_column(Text)
    company: Mapped[str] = mapped_column(Text)
    description: Mapped[str] = mapped_column(Text)
    details: Mapped[dict] = mapped_column(JSON)
    first_seen: Mapped[datetime] = mapped_column(DateTime, default=now)
    last_seen: Mapped[datetime] = mapped_column(DateTime, default=now)


class Match(Base):
    __tablename__ = "matches"
    __table_args__ = (UniqueConstraint("profile_id", "job_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    profile_id: Mapped[int] = mapped_column(ForeignKey("profiles.id"))
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id"))
    eligible: Mapped[bool] = mapped_column(Boolean)
    assessment: Mapped[dict] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(20), default="new")
    discovered_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    notified_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class Run(Base):
    __tablename__ = "runs"
    id: Mapped[int] = mapped_column(primary_key=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="running")
    fetched: Mapped[int] = mapped_column(Integer, default=0)
    new_matches: Mapped[int] = mapped_column(Integer, default=0)
    errors: Mapped[list] = mapped_column(JSON, default=list)
    coverage: Mapped[str] = mapped_column(Text, default="")


class Delivery(Base):
    __tablename__ = "deliveries"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    match_ids: Mapped[list] = mapped_column(JSON)
    recipient: Mapped[str] = mapped_column(Text)
    subject: Mapped[str] = mapped_column(Text)
    body: Mapped[str] = mapped_column(Text)
    provider_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)


class Lease(Base):
    __tablename__ = "leases"
    name: Mapped[str] = mapped_column(String(40), primary_key=True)
    token: Mapped[str] = mapped_column(String(36))
    expires_at: Mapped[datetime] = mapped_column(DateTime)


def make_engine(url):
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql+psycopg://", 1)
    elif url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+psycopg://", 1)
    engine = create_engine(url, connect_args={"check_same_thread": False, "timeout": 30} if url.startswith("sqlite") else {}, pool_pre_ping=True)
    return engine


engine = make_engine(settings.database_url)


def init_db(db=engine):
    with db.begin() as connection:
        if db.dialect.name == "postgresql":
            # Web and worker can start concurrently on a managed host.
            connection.execute(text("SELECT pg_advisory_xact_lock(8431982)"))
        Base.metadata.create_all(connection)
        with Session(bind=connection) as session:
            if not session.scalar(select(Profile).limit(1)):
                session.add(Profile(name="QA · Python · Poland", criteria={
                    "skills": ["Python"], "levels": ["junior", "mid"],
                    "country": "PL", "category": "testing", "python_optional": True,
                }))
                session.flush()


@contextmanager
def task_lock(name, db=engine, minutes=30):
    token = str(uuid4())
    acquired = False
    with Session(db) as session:
        try:
            session.add(Lease(name=name, token=token, expires_at=now() + timedelta(minutes=minutes)))
            session.commit()
            acquired = True
        except IntegrityError:
            session.rollback()
            result = session.execute(update(Lease).where(Lease.name == name, Lease.expires_at < now()).values(token=token, expires_at=now() + timedelta(minutes=minutes)))
            session.commit()
            acquired = result.rowcount == 1
    try:
        yield acquired
    finally:
        if acquired:
            with Session(db) as session:
                session.execute(update(Lease).where(Lease.name == name, Lease.token == token).values(expires_at=now()))
                session.commit()
