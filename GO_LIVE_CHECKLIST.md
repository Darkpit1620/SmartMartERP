# SmartMart ERP — Production launch checklist

The Stage 9 dashboard is a readiness aid, **not** proof that the system is secure or production ready. In particular, manual M-Pesa, card, and bank references have **not** been independently paid/verified by any provider.

## Before public access

- [ ] Run `python manage.py check` and fix every error.
- [ ] Run `python manage.py test --noinput` and investigate failing tests (especially checkout, stock reconciliation, and authorization).
- [ ] Run `python manage.py smartmart_audit` and review all severe data faults.
- [ ] Run `python manage.py check --deploy` against **production** settings, not just local development.
- [ ] Set `DEBUG=False`, a production-only `SECRET_KEY` from a secret manager or environment, precise `ALLOWED_HOSTS`, and correct CSRF trusted origins.
- [ ] Configure HTTPS/TLS and redirect HTTP to HTTPS; secure session and CSRF cookies; security headers/HSTS after HTTPS verification.
- [ ] Use an appropriate production application server and reverse proxy; never use `runserver` on a public server.
- [ ] Configure `STATIC_ROOT`, run `collectstatic`, serve static safely, and protect uploaded media/private receipts.
- [ ] Prefer PostgreSQL for a real multi-user/multi-branch operation; plan a **tested** migration from SQLite.
- [ ] Validate concurrent checkout, concurrent branch transfers, idempotency, and shortage/return scenarios using production-like database isolation.
- [ ] Configure least-privilege roles, staff approvals, account lockout/rate limiting, password reset, login audit logs, and a two-factor sign-in policy for administrators.
- [ ] Integrate and verify actual provider payment callbacks. Avoid accepting a typed M-Pesa reference as proof of payment.
- [ ] Implement/refine refunds, discounts, end-of-shift cash reconciliation, supplier credit, purchase accounting, and tax/eTIMS requirements before real-money launch.
- [ ] Obtain verified product costs/prices, tax categories, inventory counts, and supplier master data.
- [ ] Configure application monitoring, error reporting, audit retention, and alerts. Do not send secrets/PII in logs.
- [ ] Make regular encrypted, access-restricted, offsite backups; restore one to an isolated test environment and verify orders/receipts/stock balances.
- [ ] Perform permission, input validation, race-condition, and security testing with realistic accounts.
- [ ] Carry out acceptance testing with managers, cashiers, warehouse staff, finance administrators, and wholesale clerks.

Reference: [Django deployment checklist](https://docs.djangoproject.com/en/5.2/howto/deployment/checklist/).

## Local tests versus production

`DEBUG=True`, localhost, and SQLite are suitable for the current development workflow. Stage 9 leaves those settings unchanged. Production hardening is a deliberate separate rollout, never a blind switch that breaks local logins or HTTPS.
