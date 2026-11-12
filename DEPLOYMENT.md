# Render deployment preparation

Updated: 12 November 2026.

## Confirmed

- Render is connected.
- The user selected **My Workspace**.
- The selected workspace currently has no existing services or PostgreSQL databases, so this deployment will not replace an existing application.
- Source is committed locally on branch `main`.
- `.env`, the collected job database, and dashboard screenshots are excluded from Git.

## Prepared infrastructure

The root `render.yaml` requests these new resources in Frankfurt:

| Resource | Plan | Published base price checked 12 November 2026 |
|---|---|---|
| Web service | 0.5c-512mb | USD 7/month |
| Background worker | 0.5c-512mb | USD 7/month |
| PostgreSQL | 0.1c-256mb | USD 6/month |
| Database storage | 5 GB | USD 1.50/month at USD 0.30/GB |

Estimated base total: **USD 21.50/month**, before taxes, traffic/build overages, and any email-provider charges. Source: https://render.com/pricing. The actual Render plan and billing estimate take precedence.

This document is a preparation record, not approval to apply a deployment plan. The Render Blueprint workflow requires review and explicit authorization of its returned plan before approval.

## Current blocker

Render needs the source and Blueprint in a remote Git repository. Creating `Piotr-Majda/qa-job-monitor` through the connected GitHub authorization failed with `Resource not accessible by integration (createRepository)`.

An empty public repository is now available at https://github.com/Piotr-Majda/job-monitor. Source will be published with a clean initial history and without personal configuration. No Blueprint, paid infrastructure, or production deployment has been created yet.

## Next actions

1. Obtain the repository URL and confirm it is accessible to the GitHub connection and Render's Git provider.
2. Push the committed source and Blueprint, excluding local data and secrets.
3. Create a Blueprint with automatic syncing disabled and `existingResources=create_new`, then inspect the returned plan.
4. Present the actual plan and request authorization to apply it, as required by Render's Blueprint tool.
5. After authorization, approve, monitor deployment, and verify HTTPS authentication, database persistence, and real job collection.
6. Configure Resend sender secrets without placing them in Git or chat, and verify delivery to your-address@gmail.com.

Email is disabled until an authorized sender and API key are provided. No Gmail inbox access is needed.
