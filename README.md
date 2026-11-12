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

## Free cloud deployment (selected)

The current `render.yaml` creates **one Free Render web service** in Frankfurt. There is no Render database, worker, cron job, or disk. PostgreSQL is hosted on a separate **Neon Free** account, and GitHub Actions securely invokes scheduled work on the web app without keeping it online between runs.

Target recurring hosting cost: **USD 0 within provider free-tier quotas**, excluding a custom domain or optional paid upgrades. Hobby is a workspace plan, not a guarantee that every Render resource is free. Do not apply an old three-resource plan: re-plan the current repository commit first.

### 1. External database

Create a PostgreSQL project on Neon's **Free** plan, preferably in a European region near Frankfurt. Do not upgrade the account to a paid plan. Obtain a PostgreSQL connection string with TLS (`sslmode=require`) from the Neon console. Keep it private.

Configure the connection string only in the Render web service's private `DATABASE_URL` environment setting. The Blueprint declares this with `sync: false` so it is never committed. GitHub Actions never receives database credentials.

The app creates its initial schema at startup under a PostgreSQL advisory lock. Both the web app and scheduled runs use that shared database. Free cloud mode refuses SQLite so a missing connection string cannot silently lose jobs on Render's ephemeral filesystem.

Neon's published Free plan is ongoing, not a trial, but its compute, storage, and transfer limits apply. It scales down after inactivity. Monitor quotas in the provider console; do not assume the service can grow indefinitely for free.

### 2. Render dashboard

1. Link https://github.com/Piotr-Majda/job-monitor to Render using the existing Blueprint or create one from root `render.yaml`.
2. Re-plan and verify **one web service on plan `free`**, with no paid datastore or worker.
3. Supply `DATABASE_URL` through Render's secure Environment settings or the required Blueprint input. Review the actual plan before applying it.
4. Deploy. Render generates `ADMIN_PASSWORD` and `SESSION_SECRET`; retrieve the password privately from the service's Environment page to sign in.
5. The workflow defaults to the current HTTPS dashboard URL. If you deploy a fork or change the URL, set GitHub Actions variable `SCOUT_APP_URL` to the new URL and update the Render workflow-trust settings for your repository.

A Free Render service sleeps after 15 minutes without traffic and can take about a minute to wake. No keep-alive traffic is required because scheduled searches are invoked by GitHub Actions. Health checks use `/health`, which checks the web process without querying Neon, so frequent probes do not consume database compute. Schema creation is checked at startup; signed-in operators can use `/database-health` for an explicit database check.

Automatic deploys and Blueprint auto-sync remain disabled. There is no live production URL until deployment completes.

### 3. Scheduled searches and email

The workflow `.github/workflows/job-monitor.yml` invokes the app using a short-lived GitHub identity and exits when the streamed job completes. `python -m app.scheduled` remains available for manual operator runs. Its schedule is:

- **06:00 Europe/Warsaw:** collect due jobs.
- **07:00 Europe/Warsaw:** send a due digest.
- **08:17 Europe/Warsaw:** recovery check; already completed jobs and sent digests are not repeated.

The GitHub schedule includes the IANA timezone for daylight-saving changes. The Python scheduler independently checks Warsaw dates/times, collection history, and notification history. Manual **Run workflow** uses the same due-work check.

GitHub Actions uses **OpenID Connect (OIDC)** to invoke `/internal/run-due` on the dashboard. It requests a short-lived token addressed specifically to the app. The app checks GitHub's signature, issuer, audience, expiry, repository name and numeric ID, main branch, exact workflow filename, and event type before executing work. Other repositories, forks, pull requests, unsigned tokens, and anonymous requests cannot trigger the job.

The endpoint streams progress/heartbeats until due work completes. This is a scheduled job invocation, not a keep-alive ping. It works while the dashboard is closed and naturally wakes a sleeping free web service. Database task leases and delivery history prevent overlapping collection and repeated digests.

**No GitHub repository secrets are required.** Actions has `contents: read` and `id-token: write`; it receives no dashboard password, database credential, or email key. Configure these only in Render's private Environment settings:

| Name | Value |
|---|---|
| `DATABASE_URL` | Neon PostgreSQL connection string |
| `EMAIL_TO` | Your Gmail recipient address |
| `EMAIL_FROM` | An authorized Resend sender |
| `RESEND_API_KEY` | Resend API key |

The Blueprint pins `SCHEDULER_REPOSITORY` and `SCHEDULER_REPOSITORY_ID`. A fork must update those to its own name and numeric repository ID, rather than accepting arbitrary GitHub identities. `SCOUT_APP_URL` in GitHub is an optional non-secret URL override.

Without sender settings, collection still runs but no email is sent. The workflow prints a setup notice; delivery outcomes appear in the dashboard. Receiving mail in Gmail does not require inbox access.

### Free scheduling limitations

GitHub Actions schedules are **best-effort**: runs can be delayed or dropped. Public-repository scheduled workflows are disabled after **60 days without repository activity** and must be re-enabled. The 08:17 recovery check reduces the effect of one missed morning run but cannot guarantee daily execution. Check collection timestamps and enable GitHub failure notifications. Changing repository schedule variables does not edit cron expressions; edit the workflow if desired delivery times change substantially.

Standard GitHub-hosted runners in a public repository are free under GitHub's current policy; quotas, provider policies, and prices can change. Review usage rather than adding a paid runner or upgrading the database.

### Email verification and backups

Configure a Resend sender eligible for its free allowance and send one test digest to the configured Gmail address. No live inbox delivery has been verified yet. Database persistence, a real cloud scan, and a sent digest must all be checked before declaring the cloud iteration complete. Use provider-supported database export/restore for backups and monitor the database's free retention limits.

The standalone local worker and Docker Compose configuration remain available for local development; do not start a paid cloud worker for this free deployment.

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

## Migrating an existing Render database

The runtime supports an explicitly configured one-time application-data migration from inside Render's private network. Deploy with `MIGRATION_READ_ONLY=true` first, and verify `/health` reports read-only mode. Then set private `MIGRATION_TARGET_DATABASE_URL` to a **direct/unpooled** Neon URL. The replacement process copies application tables in one transaction, verifies a full content checksum, resets sequences, saves a private recovery snapshot and receipt in Neon, and serves Neon immediately after verification. It refuses a nonempty destination without a completed receipt and never overwrites already migrated data on restart. No source records are deleted.

After verifying the live app and receipt, set permanent `DATABASE_URL` to the Neon application URL and clear `MIGRATION_TARGET_DATABASE_URL` and `MIGRATION_READ_ONLY`. These migration flags are operational secrets/settings, not committed credentials. Retain the old database until verification and recovery checks are complete; removing a database from a Blueprint does not stop its billing or delete it.
