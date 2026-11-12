# QA Job Monitor — Agreement and Iteration 1 Scope

Date: 12 November 2026
Status: Product scope agreed; local prototype implemented. Render deployment and live email verification remain pending. See job-monitor/IMPLEMENTATION.md for evidence and limits.
Purpose: Record the discussion and guide implementation. This document does not authorize job submissions or deployment to a paid service.

Hosting change agreed on 12 November 2026: target USD 0 within free quotas using a Free Render web service, external Neon Free PostgreSQL, and scheduled GitHub Actions. Accept dashboard cold starts and best-effort schedules; the paid web/worker/database plan is superseded.

Source change agreed on 12 November 2026: start with Just Join IT instead of LinkedIn, using public pages without login. All other first-iteration requirements remain in scope.

## 1. Problem and objective

The user has limited time to search several job boards and misses suitable opportunities. The first iteration should discover relevant jobs, preserve descriptions and links, explain why they match, and make them available through an online dashboard and a scheduled email digest.

This is initially a personal tool for one user. Automatic application submission is a later capability.

## 2. Agreed requirements

### Independent search profiles

Each search must have independent configuration. The first profile targets QA automation. Future profiles may target Python development or other work with different salary, working-hour, location, and source requirements.

The initial QA profile is:

| Setting | Requirement |
|---|---|
| Source | Just Join IT initially |
| Roles | QA / test automation |
| Seniority | Junior or mid |
| Python | Mandatory relevant skill |
| Geography | Jobs in Poland; user is open to relocation |
| Work arrangement | Remote, hybrid, or on-site |
| Salary minimum | None configured for this profile |
| Missing salary | Include otherwise suitable jobs; display `Salary unknown` |

The earlier example of 7,000 PLN gross applies to a possible future search profile, not the initial QA profile.

### Collection and deployment

- Use Playwright where browser interaction is needed.
- Target a fully cloud-hosted solution: collection worker, scheduler, database, and dashboard.
- Local development and testing on the user's PC are acceptable.
- Collect publicly accessible Just Join IT job descriptions and source links without account credentials initially.
- Run job searches at least once daily.
- Store real collected data durably; a dashboard populated only with mock listings does not satisfy the scope.

### Dashboard

Provide an online dashboard showing:

- Job title, employer, source link, and collected description.
- Location and work arrangement, when available.
- Salary and contract details, when available; explicit unknown values otherwise.
- Match recommendation, reasons, and missing or uncertain information.
- First-seen date, source posting date when available, and last-seen date.
- Review status, with actions to save, dismiss, or manually mark as applied.
- Last successful collection time and visible collection failures.

Preserve review decisions across repeated collection runs. Distinguish a job first discovered today from a job posted today.

### Email and scheduling

Implementation follow-up: recipient agreed as `your-address@gmail.com`; Render selected as the target host; Resend selected as the sender-service implementation. Account connection and sender secrets are still needed.

- Send a scheduled digest to the user's Gmail address.
- Agreed starting defaults: search at **06:00** and send the digest at **07:00** daily.
- Interpret schedules in **Europe/Warsaw**, including daylight-saving changes.
- Keep collection and email schedules separate and configurable; an evening digest can be selected later.
- Summarize newly discovered qualifying jobs with dashboard/source links.
- Do not repeatedly notify about the same listing.
- Send no job digest when there are no new qualifying jobs.
- Summarize an initial import in one digest rather than sending one email per listing.

Receiving mail in Gmail does not require access to the user's Gmail account. Sender service and authentication method remain implementation decisions. Gmail inbox access is outside this iteration.

## 3. Proposed technical design

These are implementation recommendations, not fixed technology commitments:

- One application codebase, with a web process and a separate collection worker process.
- Playwright for browser collection, isolated from matching and notification logic.
- PostgreSQL for persistent data, usable in local development and cloud deployment.
- A scheduler that invokes collection and digest tasks independently.
- An email delivery service configured with an authorized sender.
- Authentication for the private dashboard.

Data flow:

```text
Scheduled collection -> Public listings -> Normalize and deduplicate
                                            |
                                            v
                                   Evaluate search profile
                                            |
                                            v
                                         Database
                                         /      \
                                 Dashboard    Scheduled email digest
```

Suggested records: search profiles, jobs, source listings, profile matches, collection runs, review statuses, and digest deliveries. Keep a job's source data separate from its assessment under a particular profile.

Use explicit rules for eligibility and evidence-backed reasons for ranking. A language model is optional and must not invent job facts. An unexplained numerical score alone is insufficient.

## 4. Concerns and decisions to verify during implementation

### A. Anonymous Just Join IT access — first feasibility check

- [x] Demonstrate that the intended runtime can retrieve real public listings and full descriptions without signing in.
- [ ] Check applicable access restrictions and acceptable collection frequency before enabling scheduled collection.
- [ ] Establish whether coverage is useful and repeatable; do not promise exhaustive Just Join IT coverage.
- [ ] Detect login walls, access challenges, incomplete descriptions, and extraction failures.
- [ ] Report blocked or failed collection visibly; never represent a failed run as a successful search with zero matches.
- [ ] If public access is insufficient, document evidence and agree on another source or authorized access method before changing scope. Do not bypass access challenges.

### B. Matching accuracy

- [ ] Define whether Python must be required by the employer or whether a relevant optional Python skill qualifies. Python being mandatory for the user's search is agreed; this interpretation remains open.
- [ ] Verify Python appears as a relevant skill, not merely incidental text.
- [ ] Define handling of ambiguous seniority and mixed junior/mid/senior listings.
- [ ] Distinguish jobs available to workers in Poland from remote jobs restricted to another country.
- [ ] Do not exclude jobs solely because salary is missing in the current profile.
- [ ] Preserve salary currency, period, gross/net basis, and contract type; do not compare B2B invoice amounts directly with employment gross pay.
- [ ] Review recommendations against a small manually checked set of real listings.

### C. Data quality and duplicate handling

- [ ] Preserve stable source identifiers and canonical links where available.
- [ ] Repeated scans update an existing listing rather than creating duplicates.
- [ ] Avoid merging distinct roles merely because employer and title match.
- [ ] Keep first-seen, last-seen, posting date, and collection timestamp distinct.
- [ ] Missing information remains unknown; it is not inferred as a fact.
- [ ] Define how removed, expired, edited, or reposted jobs appear and whether they warrant a new notification.
- [ ] Treat collected descriptions as untrusted content: render safely and never execute instructions embedded in them.

### D. Scheduling and notification reliability

- [ ] Verify 06:00 collection and 07:00 email in Europe/Warsaw, including daylight-saving transitions.
- [ ] Prevent overlapping runs and duplicate email delivery after retries or restarts.
- [ ] Record delivery outcomes and determine retry behavior for failed emails.
- [ ] Decide what happens if collection is still running, partially fails, or misses its window before digest time.
- [ ] A failed send must not permanently mark its listings as successfully notified.
- [ ] Decide how collection failures reach the user; dashboard visibility is required, email failure alerts are not yet agreed.

### E. Cloud operation and privacy

- [ ] Select a hosting provider, database service, email sender, and acceptable running cost before deployment.
- [ ] Obtain the recipient email address through configuration; do not hardcode it.
- [ ] Protect dashboard access and use HTTPS in the hosted environment.
- [ ] Keep hosting and email credentials in secret configuration, outside source control and logs.
- [ ] Verify database persistence, backup/restore, and basic run logging.
- [ ] Verify searches execute while the user's PC is off.
- [ ] Choose reasonable retention for descriptions, run history, and notification records.

No job-board credentials are planned for iteration 1. Hosting and email delivery can still require service credentials.

## 5. Outside iteration 1

- Automatic applications, form filling, and Easy Apply submission.
- LinkedIn account login or remote session storage.
- Additional job boards such as LinkedIn, Pracuj.pl, Protocol.it, or OLX.
- Gmail inbox reading and automatic application-status inference.
- CV upload, OCR, visual-model extraction, or CV tailoring.
- SMS, phone push, and messaging-service notifications.
- Multi-user accounts, billing, and public registration.

Future application automation should begin with Easy Apply and explicitly handle unknown answers, submission evidence, and duplicate prevention. It is not part of the discovery deliverable.

## 6. Implementation sequence

1. Validate anonymous Just Join IT collection against real listings in the intended runtime.
2. Implement the QA profile, normalization, persistent storage, deduplication, and matching.
3. Build the private dashboard using collected data and persistent review actions.
4. Add independent collection/digest schedules and reliable email delivery.
5. Validate cloud operation, persistence, and the acceptance criteria below.

## 7. Iteration 1 acceptance criteria

- [x] A real collection run saves accessible job descriptions and working source links; provenance and collection time are visible.
- [x] QA profile rules are applied, with clear explanations and unknown fields identified.
- [x] Search settings are stored independently so later profiles can use different rules.
- [x] The dashboard displays real persisted results and preserves review actions across refreshes and scans.
- [ ] Repeated collection does not create duplicate listings or repeated notifications.
- [ ] Collection runs at least daily, with the agreed starting schedule of 06:00 Europe/Warsaw.
- [ ] The 07:00 digest reaches the configured Gmail recipient and links to newly discovered qualifying jobs.
- [ ] An empty successful run and a collection failure are distinguishable.
- [ ] Scheduled operation works in the cloud while the user's PC is off.
- [x] No application is submitted and no Gmail inbox access is requested by iteration 1.

Validation must use real collected listings and an actual delivered test email. Mock data may support development but cannot establish collection feasibility or completion. If the source has no qualifying matches during validation, use a retained real sample for dashboard verification and clearly identify its collection date.
