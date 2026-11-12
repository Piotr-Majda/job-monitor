# Scout — personal QA job monitor

A working first iteration using **public Just Join IT pages**, with no job-board login. It collects full descriptions, evaluates independent search profiles, stores results, and provides a private dashboard and scheduled email digest.

Initial profile: junior/mid QA test automation, Python required, anywhere in Poland, any work arrangement, relocation accepted. Salary is optional and displayed as unknown when unavailable. Python mentioned as an optional skill currently remains eligible with evidence for review. Clearly senior/leadership roles are excluded.

## Run locally

Requires Python 3.12+ and uv. From this project directory:

```bash
uv sync --frozen
uv run python -m app.cli init
uv run python -m app.cli collect
uv run uvicorn app.web:app --host 127.0.0.1 --port 8000
```

Open <http://localhost:8000>. In another terminal, start the scheduler:

```bash
uv run python -m app.worker
```

The local default uses SQLite in `data/jobs.db`. It requires no external database. The production container configuration uses PostgreSQL. Both use the same SQLAlchemy models and service code.

Environment variables can be loaded from an ignored `.env` file with:

```bash
uv run --env-file .env uvicorn app.web:app --host 127.0.0.1 --port 8000
uv run --env-file .env python -m app.worker
```

Without an admin password, local development has no login. Bind unauthenticated local previews only to loopback. Production refuses startup without a strong password, session secret, and HTTPS application URL.

## Run with PostgreSQL and Docker

```bash
cp .env.example .env
# Edit .env: replace passwords and session secret. Use a URL-safe database password.
docker compose up --build -d
docker compose exec web python -m app.cli collect
```

Open <http://localhost:8000> and sign in using `ADMIN_PASSWORD`. The worker starts after web initialization and catches up a missed daily search on startup. PostgreSQL data survives container restarts in the named `postgres-data` volume. Do not remove that volume unless intentionally deleting the database.

Local database snapshots are not automatically imported into PostgreSQL. Run the collector against the target database to populate it.

## Schedule

Defaults are **06:00 collection** and **07:00 digest**, in `Europe/Warsaw`, including daylight-saving changes. Set `SEARCH_TIME` and `DIGEST_TIME` independently using `HH:MM`, then restart the worker. A five-minute scheduler tick checks whether the day's task has run; normally work begins at the configured minute, with up to five minutes of scheduling delay.

The scheduler runs in a separate service, independent of the dashboard or user's PC. There should be one worker instance. Database leases prevent overlapping manual and scheduled tasks. A collection has a 25-minute timeout and a 30-minute lease.

After an outage, the worker catches up today's tasks if their configured time has passed. It does not replay old daily digests. A failed collection is visible and may be retried manually; automatic collection attempts are limited to one daily run. If collection is still running at digest time, delivery is deferred to a later tick. Partial runs preserve successfully collected listings and show errors.

## Email to Gmail

The app uses the Resend HTTPS API to send to your Gmail address. It does not read Gmail or require Google account credentials. Provider selection is a replaceable service boundary; Resend is the implemented default, not an existing configured account.

1. Create a sender-service account and configure an authorized sender. Resend's test sender can be limited to the account owner's verified recipient; general delivery requires a verified domain. Check the provider's current quotas and pricing before activation.
2. Configure `EMAIL_TO`, `EMAIL_FROM`, and `RESEND_API_KEY` through your host's secret settings, or an ignored `.env` locally.
3. Restart web and worker. The dashboard will show that the sender is configured.
4. Preview the content, then test actual delivery to your configured address:

```bash
uv run --env-file .env python -m app.cli preview-email
uv run --env-file .env python -m app.cli digest
```

Email previews are saved to `data/digest-preview.html`. The preview command sends nothing and may include jobs already notified; the actual digest includes only eligible, unnotified, new/saved matches from enabled profiles.

A digest outbox stores the recipient, immutable content, and provider idempotency key before sending. Failed sends preserve notification eligibility and retry with the same key. Pending sends older than 23 hours require manual provider verification to avoid duplicates beyond Resend's idempotency window. In this prototype an operator resolves `needs_review` records in the database after checking provider logs; no dashboard resolution button is implemented yet.

Actual Gmail delivery has **not** been verified in this workspace because sender credentials and recipient configuration are absent. Mock-provider tests verify failure/retry bookkeeping, not inbox arrival.

## Deploy on Render

`render.yaml` defines a web service, a background worker, and PostgreSQL in Frankfurt. It has been validated against Render's current public Blueprint schema. It requests **paid instance types**; review the live cost estimate in Render before applying it.

1. Put the contents of this project directory in a Git repository, with `render.yaml` at the repository root. Do not upload `.env`, `.venv`, or the local database.
2. Connect the repository in Render and create a Blueprint from `render.yaml`.
3. Review services and pricing, then deploy. Database schema initialization runs before web startup; PostgreSQL advisory locking also protects concurrent web/worker initialization.
4. Open the generated HTTPS web URL. Read the generated `ADMIN_PASSWORD` from the web service's Environment settings and use it to sign in. Do not paste it into chat.
5. On `scout-web`, set `EMAIL_FROM` to your authorized Resend sender and `RESEND_API_KEY` through secret environment settings. Set `EMAIL_TO` to your Gmail address in Render; it is intentionally blank in the public Blueprint. The worker references the web service's settings; sync the Blueprint and redeploy both services after changing shared values.
6. Verify a real collection, check the dashboard's collection health, and verify a delivered test digest. The worker catches up a due daily search automatically on startup.

Render's `postgres://` connection strings are normalized to the installed psycopg driver. The web process uses `RENDER_EXTERNAL_URL` as its HTTPS application URL; the worker references that same URL for email links. Email starts disabled until sender settings are provided. Automatic deploys are disabled in the blueprint to keep deployment explicit.

Render is connected for this chat. Remote source repository access and sender secrets are still required to publish and validate this deployment. See `DEPLOYMENT.md` for current preparation state and the hosting estimate. A schema-valid blueprint is not proof of a running production service.

## Other cloud hosts

The intended deployment is a container-capable host with:

- One web service, using the Dockerfile's default command and internal port 8000.
- One background worker, using `python -m app.worker` from the same image.
- One PostgreSQL database, shared by web and worker.
- HTTPS ingress and a private dashboard password.

A small VPS with Docker Compose and a TLS reverse proxy is a straightforward option. A managed container host with a web service, worker, and PostgreSQL also fits. No provider, paid resources, or production domain have been provisioned by this implementation.

Configure both processes with the same `DATABASE_URL` (`postgresql+psycopg://...`), `ENVIRONMENT=production`, `APP_URL=https://your-domain`, `ADMIN_PASSWORD` (16+ characters), and `SESSION_SECRET` (32+ random characters), plus collection/email settings. Initialize schema with `python -m app.cli init` before starting processes. Use a TLS reverse proxy or the host's HTTPS ingress; the Python container itself serves HTTP internally.

For a VPS, keep Compose's loopback binding and proxy HTTPS to port 8000. Configure database backups, monitor worker/container restarts, and verify one collection and one actual email after deployment. `GET /health` checks database connectivity but does not establish collector or email health; those are shown separately in the dashboard.

The schema is an initial prototype with `create_all`, not a versioned migration system. Add reviewed migrations before changing a deployed database schema. Do not delete production data to upgrade.

## Collection behavior and limits

- Public Testing category pages are fetched with Playwright's request client. Their server-rendered JSON-LD provides links and full descriptions; no Chromium installation is required for collection.
- The collector checks `robots.txt`, waits at least one second between requests, and never calls private/disallowed API routes.
- Default coverage is at most three pages / 150 distinct links per run. Coverage is shown explicitly; it is not exhaustive board coverage.
- Listing pages can overlap as new jobs arrive. Stable source slugs deduplicate listings. Repeated page contents stop pagination with a visible coverage warning.
- A 403/429 stops further detail collection; source challenges are not bypassed. Missing structured data is an error, not a successful empty result.
- Closed jobs are excluded if the source expiry is known. Unseen listings are not automatically marked expired, because bounded collection does not prove removal. Reposts with a new slug can appear as a new opportunity.
- Descriptions are stored as plain text and escaped in dashboard/email output. A model is not used to invent facts or experience.
- Profile editing changes name, required skills, junior/mid levels, and enabled status. Geography remains Poland and source/category remain Just Join IT / Testing in this iteration. Independent per-profile collection schedules and other categories/sources remain future work.
- Matching is heuristic. Relevant mentions of Python can include optional requirements or secondary responsibilities; inspect the evidence. This tool recommends review and never submits applications.

## Verification

```bash
uv run pytest -q
```

Tests cover source/schema failures, seniority/country filtering, unknown salary, duplicates and persistent review state, independent profiles, database leases, email retries/idempotency, authentication, CSRF, and escaped untrusted content. Real-data collection and browser checks are recorded in `IMPLEMENTATION.md`.

The agreed scope and remaining acceptance checklist are in `docs/iteration-1-agreement.md`.
