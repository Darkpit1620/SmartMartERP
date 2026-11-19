# SmartMart ERP — Stage 11D: Staging verification

**Purpose:** Verify Render staging and privacy controls before a live supermarket rollout. This stage does not deploy hosting, migrate data, process payments, or grant access.

## How to use

1. Install Stage 10D and Stage 11B first (Stage 11D won't replace those settings).
2. Extract Stage 11D into your **existing** SmartMart ERP project. Run `python install_smartmart_stage11d.py`.
3. On your Windows laptop: `python smartmart_stage11d_verify.py --mode local`
4. Optionally test all apps locally: `python smartmart_stage11d_verify.py --mode local --full-tests` (Django's separate test database).
5. **Only once Render reports Live**, check external HTTPS without credentials: `python smartmart_stage11d_verify.py --mode remote --url https://YOUR-ACTUAL-HOST.onrender.com`.
6. Commit `smartmart_stage11d_verify.py` to your already-private GitHub repo after checking its contents. This enables the next step.
7. **On the Render web service's Shell**: `python smartmart_stage11d_verify.py --mode server`, which uses staging env vars already configured by Stage 11B.

## What each check actually does

| Mode | Checks | Does NOT do |
|---|---|---|
| `local` | deployment files, Git-tracked file names, `.gitignore`, Git remote, Django `check` | No code uploads, migrations, business writes |
| `local --full-tests` | Adds all Django tests in Django's temporary test DB | Does not import real production data or run on staging DB |
| `remote` | HTTP GET over HTTPS, security response headers, anonymous access to protected URLs | No login, no email, no transactions, no changes |
| `server` | Django staging settings, PostgreSQL `SELECT 1`, pending migrations (`migrate --check`), HTTPS cookie settings, deployed checks | **Does not run `migrate` to apply schema**, doesn't create users/sales |

Some review items are expected: HSTS is disabled during the initial staging rollout, and Django's own HTTPS redirect is disabled because Render terminates TLS at its edge. **Verify that Render actually redirects HTTP to HTTPS.** Django `check --deploy` alone cannot prove your app's authorization model is safe.

## Required manual verification before real business use

- Render service status is **Live**; homepage HTTPS certificate is valid; HTTP requests redirect to HTTPS.
- Persistent disk `/var/data` survives a full service restart and a deployment, including any test uploaded files. **The disk is unavailable in Render build and pre-deploy phases**.
- PostgreSQL data persists after a restart and separate recovery test. Create an off-platform database backup and demonstrate a restore to a new isolated database. **The local SQLite backup tool does not back up PostgreSQL**.
- Test with **fake** customers and synthetic stock: supplier purchase -> goods receipt -> retail POS -> wholesale -> transfer -> expense approval, then check receipts, prices, stock movements and financial reconciliation.
- Verify branch isolation and that a cashier, warehouse employee and unapproved employee cannot access head-office functions. Check with authenticated sessions, not just anonymous GETs.
- Check upload authorization and privacy. A persistent disk prevents data loss but does not secure private files from unauthorized access.
- Confirm live card/M-Pesa verification, webhook signature validation, idempotency, refunds, chargebacks and settlement reconciliation. **Manual transaction references in SmartMart do not establish receipt of funds**.
- Verify tax registration, receipt requirements, KRA eTIMS integration and data/privacy obligations with qualified professionals.
- Add error monitoring, application audit logging, patch plan, password reset/email reliability, rate limiting, recovery procedures and incident-response ownership.
- Keep staging distinct from real customers and business finances. A private repository does **not** restrict public access to the hosted website.

## Troubleshooting

- **Local files missing:** Extract the Stage 10D and Stage 11B packages, or rerun their verified installers, and retry.
- **Git preflight fails:** Inspect file paths before Git push. `git rm --cached -- <path>` removes a tracked file from Git index only; do not delete real database files.
- **Render check fails because environment variable missing:** Add the variable in Render Dashboard only; do not commit an `.env` containing secrets.
- **PostgreSQL migration check fails:** Review deployment logs and pre-deploy command from Stage 11B. Apply migrations only through a deliberate deployment procedure with a backup.
- **Anonymous admin path returns 200:** Treat as a possible serious access-control exposure and investigate before launch.
- **Remote request returns 404:** Verify Stage 9/10C modules are installed and URL routing matches.
- **Remote request returns HTTPS error:** Confirm the actual Render hostname, active status and TLS certificate. No exception is made for self-signed certificates.

## Reference docs

- Render Django: https://render.com/docs/deploy-django
- Render deploys/pre-deploy steps: https://render.com/docs/deploys
- Render persistent disks: https://render.com/docs/disks
- Django security checks: https://docs.djangoproject.com/en/5.2/ref/checks/
