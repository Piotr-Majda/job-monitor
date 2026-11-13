# Deployment status — 13 November 2026

## Live application

- Dashboard: https://scout-web-47vk.onrender.com
- Render web service: **Free**, Frankfurt; automatic deploys and Blueprint auto-sync are disabled.
- Database: **Neon Free**, Frankfurt, with automatic scale-to-zero.
- Permanent database connection is stored only in Render's private environment settings.
- The database migration has completed, the checksum was verified, and the dashboard is writable on Neon.
- Migration flags have been cleared. Restarting the application no longer depends on the old database.

## Migration verification

The old cloud database contained one search profile and no collected jobs, reviews, or email deliveries. These were copied in an atomic transaction. The private Neon database retains a `render-to-neon-v1` receipt and recovery snapshot. The deployed `/health` endpoint confirms `database_provider=neon` and `migration_read_only=false` without making database queries.

## Scheduled searches

GitHub Actions invokes the app with a short-lived signed identity. The app validates issuer, audience, expiry, repository name and numeric ID, branch, exact workflow, and event type. Custom GitHub subject templates are supported because authorization uses explicit signed identity claims rather than assuming the default subject format. No database or email credential is stored in GitHub.

The first live invocation authenticated successfully and completed without errors: **149 real Just Join IT descriptions and 16 qualifying matches** were saved in Neon. Verified workflow: https://github.com/Piotr-Majda/job-monitor/actions/runs/43384022795. The run reported that email is not configured, so no digest was sent.

Schedules target 06:00 collection, 07:00 email, and 08:17 recovery in Europe/Warsaw. Free GitHub schedules can be delayed or dropped and are disabled after 60 days without repository activity. The Free Render app can take about a minute to wake.

## Remaining account setup

1. **Remove the unused paid Render database to stop its remaining charges.** Removing it from a Blueprint does not delete it. The connected Render toolset has no deletion operation; the account owner must do this in the Render Dashboard after reviewing the verified migration.
2. Configure an authorized Resend sender and API key privately in Render if they are not yet present. The recipient has been configured privately. No API key or personal email address belongs in this public repository.
3. Verify a delivered test email once sender configuration is complete.

The target recurring application hosting cost is USD 0 within provider free quotas, but the old paid Render database continues billing until it is deleted. Do not delete the Neon project or the Free web service.
