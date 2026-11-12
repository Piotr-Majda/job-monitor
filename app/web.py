import hmac
import asyncio
import json
import logging
import os
import secrets
from contextlib import asynccontextmanager
from datetime import timezone
from zoneinfo import ZoneInfo

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session
from sqlalchemy.engine import make_url
from starlette.middleware.sessions import SessionMiddleware

from .config import ROOT, settings
from .db import Base, Delivery, Job, Match, Profile, Run, engine, init_db
from .services import reassess_profile
from .oidc import verify_workflow_token


@asynccontextmanager
async def lifespan(app):
    settings.validate()
    init_db()
    if settings.migration_read_only:
        with Session(engine) as session:
            counts = {table.name: session.scalar(select(func.count()).select_from(table)) for table in Base.metadata.sorted_tables}
        logging.warning("Migration read-only mode; source row counts: %s", counts)
    yield


app = FastAPI(title="Scout · QA job monitor", lifespan=lifespan, docs_url=None, redoc_url=None)
app.add_middleware(SessionMiddleware, secret_key=settings.session_secret or secrets.token_hex(32), same_site="strict", https_only=settings.production, max_age=12 * 3600)
app.mount("/static", StaticFiles(directory=ROOT / "app/static"), name="static")
templates = Jinja2Templates(directory=ROOT / "app/templates")


def localtime(value):
    if not value:
        return "Not yet"
    return value.replace(tzinfo=timezone.utc).astimezone(ZoneInfo(settings.timezone)).strftime("%d %b, %H:%M")


def salary_label(details):
    salary = details.get("salary")
    if not salary:
        return "Salary unknown"
    value = salary.get("value", {})
    if not isinstance(value, dict):
        return f"{value} {salary.get('currency', '')}"
    low, high = value.get("minValue", value.get("value")), value.get("maxValue")
    if low is None and high is None:
        return "Salary unknown"
    return f"{low if low is not None else '?'}{f' – {high}' if high else ''} {salary.get('currency', '')} / {value.get('unitText', '?').lower()}"


templates.env.filters["localtime"] = localtime
templates.env.filters["salary"] = salary_label


def require_user(request):
    if settings.admin_password and not request.session.get("authenticated"):
        raise HTTPException(401, "Sign in required")


def require_csrf(request, token):
    expected = request.session.get("csrf", "")
    if not expected or not hmac.compare_digest(expected, token):
        raise HTTPException(403, "Expired form; refresh and try again")


def context(request, **kwargs):
    request.session.setdefault("csrf", secrets.token_urlsafe(32))
    return {"request": request, "csrf": request.session["csrf"], "config": settings, **kwargs}


@app.middleware("http")
async def security_headers(request, call_next):
    if settings.migration_read_only and request.method not in ("GET", "HEAD", "OPTIONS") and request.url.path not in ("/login", "/logout"):
        from fastapi.responses import JSONResponse
        return JSONResponse({"detail": "Database migration in progress. Review actions are temporarily paused."}, status_code=503)
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "same-origin"
    response.headers["Content-Security-Policy"] = "default-src 'self'; style-src 'self'; script-src 'self'; img-src 'self' data:; form-action 'self'; frame-ancestors 'none'"
    if not request.url.path.startswith("/static"):
        response.headers["Cache-Control"] = "no-store"
    return response


@app.get("/health")
def health():
    # Frequent platform probes must not keep a serverless database awake.
    # Startup verifies the database; an authenticated on-demand check is below.
    host = make_url(settings.database_url).host or ""
    return {"status": "ok", "database_provider": "neon" if host.endswith(".neon.tech") else "other",
            "migration_read_only": settings.migration_read_only, "revision": os.getenv("RENDER_GIT_COMMIT", "local")[:12]}


@app.get("/database-health")
def database_health(request: Request):
    require_user(request)
    with Session(engine) as session:
        session.execute(select(1))
    return {"status": "ok"}


@app.post("/internal/run-due")
async def scheduled_invocation(request: Request):
    await asyncio.to_thread(verify_workflow_token, request.headers.get("authorization", ""))
    from contextlib import suppress
    from .worker import tick

    async def progress():
        task = asyncio.create_task(tick())
        try:
            yield json.dumps({"status": "started"}) + "\n"
            while not task.done():
                done, _ = await asyncio.wait({task}, timeout=10)
                if not done:
                    yield json.dumps({"status": "running"}) + "\n"
            await task
            yield json.dumps({"status": "completed", "email_configured": settings.email_ready}) + "\n"
        except Exception as error:
            logging.error("Scheduled invocation failed (%s)", type(error).__name__)
            yield json.dumps({"status": "failed"}) + "\n"
        finally:
            if not task.done():
                task.cancel()
                with suppress(asyncio.CancelledError):
                    await task

    return StreamingResponse(progress(), media_type="application/x-ndjson", headers={"X-Accel-Buffering": "no"})


@app.get("/login")
def login_page(request: Request):
    return templates.TemplateResponse(request=request, name="login.html", context=context(request, error=None))


@app.post("/login")
async def login(request: Request, password: str = Form(), csrf: str = Form()):
    import asyncio
    require_csrf(request, csrf)
    if not settings.admin_password or hmac.compare_digest(password.encode(), settings.admin_password.encode()):
        request.session.clear()
        request.session["authenticated"] = True
        return RedirectResponse("/", status_code=303)
    await asyncio.sleep(1)
    return templates.TemplateResponse(request=request, name="login.html", context=context(request, error="Incorrect password"), status_code=401)


@app.post("/logout")
def logout(request: Request, csrf: str = Form()):
    require_csrf(request, csrf)
    request.session.clear()
    return RedirectResponse("/login", status_code=303)


@app.get("/")
def dashboard(request: Request, profile: int | None = None, view: str = "inbox", q: str = ""):
    if settings.admin_password and not request.session.get("authenticated"):
        return RedirectResponse("/login", status_code=303)
    if view not in ("inbox", "saved", "applied", "dismissed", "outside"):
        view = "inbox"
    with Session(engine) as session:
        profiles = list(session.scalars(select(Profile).order_by(Profile.id)))
        active = next((p for p in profiles if p.id == profile), profiles[0])
        query = select(Match, Job).join(Job, Match.job_id == Job.id).where(Match.profile_id == active.id)
        if view == "outside":
            query = query.where(Match.eligible.is_(False))
        elif view == "inbox":
            query = query.where(Match.eligible.is_(True), Match.status.in_(["new", "saved"]))
        else:
            query = query.where(Match.status == view)
        if q:
            query = query.where((Job.title.ilike(f"%{q[:120]}%")) | (Job.company.ilike(f"%{q[:120]}%")))
        rows = list(session.execute(query.order_by(case((Job.details["level"].as_string() == "unknown", 1), else_=0), Match.discovered_at.desc()).limit(200)))
        runs = list(session.scalars(select(Run).order_by(Run.started_at.desc()).limit(5)))
        success = session.scalar(select(Run).where(Run.status == "success").order_by(Run.started_at.desc()).limit(1))
        deliveries = list(session.scalars(select(Delivery).order_by(Delivery.created_at.desc()).limit(3)))
        counts = dict(session.execute(select(Match.status, func.count()).where(Match.profile_id == active.id, Match.eligible.is_(True)).group_by(Match.status)).all())
        total = session.scalar(select(func.count(Job.id)))
        return templates.TemplateResponse(request=request, name="dashboard.html", context=context(request,
            profiles=profiles, active=active, rows=rows, runs=runs, success=success,
            deliveries=deliveries, counts=counts, total=total, view=view, q=q,
        ))


@app.post("/matches/{match_id}/status")
def status(request: Request, match_id: int, status: str = Form(), csrf: str = Form()):
    require_user(request)
    require_csrf(request, csrf)
    if status not in ("new", "saved", "dismissed", "applied"):
        raise HTTPException(400, "Unknown review status")
    with Session(engine) as session:
        match = session.get(Match, match_id)
        if not match:
            raise HTTPException(404)
        match.status = status
        session.commit()
        profile_id = match.profile_id
    return RedirectResponse(f"/?profile={profile_id}", status_code=303)


@app.post("/profiles")
def profile_save(request: Request, name: str = Form(), skills: str = Form("Python"), levels: str = Form("junior,mid"), profile_id: int = Form(0), enabled: str = Form("false"), csrf: str = Form()):
    require_user(request)
    require_csrf(request, csrf)
    names = [x.strip() for x in skills.split(",") if x.strip()]
    seniorities = [x.strip().lower() for x in levels.split(",") if x.strip()]
    if not name.strip() or len(name) > 120 or not names or len(skills) > 250 or not seniorities or not set(seniorities) <= {"junior", "mid"}:
        raise HTTPException(400, "Provide a profile name, required skills, and junior/mid levels")
    with Session(engine) as session:
        profile = session.get(Profile, profile_id) if profile_id else Profile()
        if profile is None:
            raise HTTPException(404)
        profile.name, profile.enabled = name.strip(), enabled == "true"
        profile.criteria = {"skills": names, "levels": seniorities, "country": "PL", "category": "testing", "python_optional": True}
        session.add(profile)
        session.commit()
        profile_id = profile.id
    reassess_profile(profile_id)
    return RedirectResponse(f"/?profile={profile_id}", status_code=303)
