# Current deployment: free hobby variant

Updated: 12 November 2026.

The user selected the **free variant**, replacing the previously planned USD 21.50/month multi-service configuration. No paid resources were approved or deployed.

## Selected resources

- One Free Render web service in Frankfurt, using the root `render.yaml`.
- An external Neon **Free** PostgreSQL project, shared by the dashboard and scheduled tasks.
- GitHub Actions in the public repository for 06:00 collection, 07:00 email, and an 08:17 recovery check, using Europe/Warsaw time. Invocations use verified short-lived GitHub OIDC tokens; all credentials stay in Render.
- Resend email delivery within its free allowance, once an authorized sender is configured.

Target recurring hosting cost is **USD 0 within free-tier limits**. The dashboard can cold-start, scheduled jobs can be delayed or dropped, and GitHub disables inactive public-repository schedules after 60 days.

## Source and account state

Repository: https://github.com/Piotr-Majda/job-monitor, branch `main`.

Render is connected and **My Workspace** is confirmed. The existing Blueprint must be re-planned against this commit before approval. Earlier plans with a database and worker are superseded; do not apply them.

Neon is connected and a Free project has been created in Frankfurt. The external database connection string must be provided privately to Render. Email sender secrets are still needed. No secrets or personal recipient address belong in this public repository.

## Deployment checklist

1. Connect Neon and create/select a project explicitly on the Free plan.
2. Supply its TLS connection string privately as `DATABASE_URL` in Render.
3. Review the new Render plan: exactly one Free web service, no paid database/worker/cron/disk.
4. Apply only the reviewed, authorized plan; verify HTTPS login and database-backed dashboard data.
5. Confirm the workflow URL and repository identity pins, and configure recipient/sender/API-key settings privately in Render.
6. Run the Actions workflow, verify real descriptions persist, and verify one actual email reaches Gmail.

See README.md for detailed setup and provider limitations.
