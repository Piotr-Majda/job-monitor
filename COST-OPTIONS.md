# Lower-cost hosting options

Checked against provider documentation on 12 November 2026. The original multi-service deployment has not been approved or deployed. **Option A (free variant) is now selected.**

## Why the original plan costs about USD 21.50/month

Render's Hobby **workspace** has no monthly subscription, but compute and storage are separate charges. The original Blueprint requested a USD 7/month web service, USD 7/month continuously running worker, USD 6/month PostgreSQL instance, and USD 1.50/month database storage.

A personal monitor that scans daily does not require this separation. The original setup can be simplified.

## Option A: target USD 0 within free quotas

- Free Render web service for the private dashboard.
- An external PostgreSQL provider with a suitable ongoing free tier; a separate account and connection string are needed. Provider and current quotas must be verified before selecting one.
- Scheduled GitHub Actions runs from the public repository for collection and email delivery, using repository secrets for database and email credentials.
- An email provider's free allowance, if the configured recipient/sender and message volume qualify.

The dashboard can sleep after 15 minutes of inactivity and take about a minute to wake. Scheduled GitHub Actions are best-effort: jobs can be delayed or dropped, and public-repository schedules are disabled after 60 days without repository activity. This is a hobby compromise, not a guarantee of an exact daily delivery time. Storage and notification state must remain in the external database, never on the free web service's ephemeral filesystem.

This option changes the scheduler and database hosting. The free web service does not need artificial keep-alive requests because scheduled work runs separately.

## Option B: about USD 7.25/month, entirely on Render

- One USD 7/month paid web service running the dashboard and in-process scheduler.
- SQLite on a 1 GB persistent disk at USD 0.25/month.
- No separate worker or managed PostgreSQL instance.
- Email-provider fees, if any, are separate.

This requires embedding the existing scheduler in the web application's lifecycle, running exactly one web process/instance, configuring the SQLite path beneath the disk mount, initializing the database at runtime, and implementing database-native backups. A service with a disk has brief downtime during deployment and cannot scale horizontally. The disk is unavailable during build/pre-deploy, so the original pre-deploy database initialization command must be removed for this variant.

This option keeps scheduling independent of whether the user has the dashboard open, without requiring an external database account.

## Why not just select every Render Free option?

- Free Render Postgres expires after 30 days, followed by a limited upgrade grace period; it is unsuitable for indefinite application history.
- Free web-service local files disappear on spin-down, restart, and deployment, so SQLite there would lose saved jobs and review state.
- Free web services sleep, so an in-process scheduler cannot provide dependable unattended execution.
- Render cron services are billed separately, with a USD 1/month minimum per cron service. They can reduce worker cost, but do not make an all-Render deployment free indefinitely.

Prices exclude taxes and usage overages. The free variant is selected and prepared in the root Blueprint and GitHub workflow. It has not yet been deployed; do not apply the original three-resource plan.

## References

- https://render.com/pricing
- https://render.com/docs/free
- https://render.com/docs/disks
- https://render.com/docs/cronjobs
- https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule
