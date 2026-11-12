> Deployment update: the user selected the free variant. The current root Blueprint contains only a Free Render dashboard; Neon Free PostgreSQL and GitHub Actions replace the paid database and worker. See README.md and DEPLOYMENT.md for current setup. The earlier multi-service deployment below is historical and must not be applied.

# Iteration 1 implementation record

Date: 12 November 2026. Source: Just Join IT, replacing LinkedIn by user agreement.

## Implemented

- Public-page collection using Playwright's request client, with robots checks, delays, bounded pagination, full structured job descriptions, and visible failures.
- Independent stored QA search profiles: required skills, junior/mid levels, name, and enabled state. All currently use the Testing category and Poland geography.
- Persistent job/match storage; repeat scans retain first-seen dates, review status, and notification history.
- Private dashboard with source links, descriptions, salary/unknown labels, evidence-based recommendations, saved/dismissed/applied views, and collection health.
- Separate worker with daily 06:00 collection and 07:00 email defaults in Europe/Warsaw, restart catch-up, and database task leases.
- Resend digest implementation with a durable outbox, provider idempotency keys, and retry bookkeeping. Recipient configured separately through deployment environment variables; no personal address is committed.
- Docker/Compose deployment files and a Render Blueprint for web, worker, and PostgreSQL in Frankfurt.

## Verification performed

| Check | Observed result |
|---|---|
| First real collection | 50 full descriptions; successful run |
| Second real collection | 60 full descriptions over two listing pages; successful run |
| Database after both scans | 60 distinct real jobs, not 110; 10 currently qualifying matches after matching fixes |
| Automated suite | 25 tests passed |
| Desktop/mobile browser checks | Real cards, save/restore persistence, profile dialog, no JavaScript errors, no mobile horizontal overflow |
| PostgreSQL smoke checks | Schema creation, matching, deduplication, and database leases passed |
| Render-style database URL | `postgres://` normalization and concurrent PostgreSQL initialization passed |
| Docker build | Succeeded; source permissions and Playwright's libatomic dependency corrected |
| Non-root container collection | One real public listing fetched successfully, without account login |
| Render Blueprint | Validated against https://render.com/schema/render.yaml.json |
| Email preview | Generated from real matching jobs in data/digest-preview.html |
| Provider failure/retry | Mock-provider tests passed; a failed send remains unnotified, and retry reuses the outbox idempotency key |

The test suite emits one upstream Starlette TestClient deprecation warning about its HTTP client. It does not affect these passing assertions.

During Docker verification, intermediate images exhausted the small workspace disk. Task-created intermediate images/cache and test containers were removed, and the final tests and container collection then passed. This was an execution-workspace limit, not a production sizing measurement.

## Earlier verification and outstanding cloud checks

1. Render is now connected and My Workspace is confirmed. Source is now published at https://github.com/Piotr-Majda/job-monitor. The Blueprint exists; account setup, successful planning, review, and approval remain before deployment.
2. Configure a Resend account, API key, and authorized sender through secret environment settings. Sender keys are absent; no live email was sent.
3. Verify a test digest actually arrives at the user's Gmail address and its dashboard links use the deployed HTTPS URL.
4. Verify scheduled collection and email in the deployed worker, independent of the user's PC.
5. Configure production database backups and complete the remaining acceptance checks in the agreement document.

No paid services have been provisioned and no live production dashboard URL exists yet. The workspace preview is not permanent hosting.

## Known limits and open matching choices

- Python is mandatory as a relevant mention. A Python skill listed as optional currently remains eligible and is shown with evidence for user review. Whether optional-only mentions should be excluded still needs a product decision.
- Recommendations use deterministic rules and need human review. Broad descriptions can mention automation or Python in secondary responsibilities.
- Salary values retain their source currency and period; no salary minimum or cross-contract conversion is applied.
- Coverage is limited to the configured public pages, not all jobs on the board. Source HTML and access policy can change.
- Jobs with unknown seniority are marked for review. Clearly senior/leadership titles are excluded.
- Unseen listings are not automatically declared closed. New source slugs are treated as new opportunities, so reposts can reappear.
- The dashboard supports independent matching profiles; independent profile schedules, non-QA sources/categories, and salary/hour constraints remain future extensions.
- Email sends older than the provider idempotency window require manual operator review.
- The database schema is an initial version; future deployed schema changes need reviewed migrations.
- No application submission, CV processing, or Gmail inbox access is implemented.

## Included artifacts

- `data/jobs.db`: a local snapshot of real collected listings; no account credentials.
- `data/dashboard-desktop.png` and `data/dashboard-mobile.png`: dashboard screenshots.
- `data/digest-preview.html`: an email preview; not a sent message.
- `.env.example`: setup values with the agreed recipient; real sender secrets are not included.

The downloadable archive includes these real-data artifacts for local testing. Do not commit the database, personal environment files, or future sender secrets to a public repository.
