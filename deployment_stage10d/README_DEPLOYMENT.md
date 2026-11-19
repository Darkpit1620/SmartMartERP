# SmartMart ERP Stage 10D — Safe deployment preparation

This package is **preparation, not a live deployment**. It does **not** change `config/settings.py`, your local SQLite database, your POS, or the local `127.0.0.1:8002` server. It creates a separate `config/settings_production.py` module and appends private-file rules to `.gitignore`.

## Install on Windows (local SmartMartERP project)

1. Stop the Django development server (`Ctrl+C`).
2. Open VS Code PowerShell in your existing SmartMartERP folder.
3. Extract `SmartMartERP_Stage10D_Deployment_Prep.zip` into the root folder with `Expand-Archive ... -Force`.
4. Run `python install_smartmart_stage10d.py`.
5. Run `python smartmart_deployment_doctor.py`.
6. Run `python manage.py test --noinput` and `python manage.py smartmart_audit` to ensure your current application still works.
7. Continue local development with `python manage.py runserver 8002`.

The **private backup** created before installation is outside the project under `Documents/SmartMartERP_Backups` by default. Do not upload it publicly.

## Important prerequisites before going live

- Choose a Linux hosting provider with trusted HTTPS reverse proxy and domain name.
- Provision a managed PostgreSQL database, private credentials, automated snapshots, and a tested restore procedure.
- Provide **persistent private media storage**. On ephemeral hosts, use object storage via a suitable backend rather than the local filesystem. Uploaded files should not be publicly executable or accessible without authorization.
- Use a trusted email provider for any email notifications.
- Choose a real payments provider and integrate callback verification, reconciliation, refunds, and transaction idempotency before accepting payments online.
- Confirm tax requirements (including KRA eTIMS if applicable), privacy requirements, staff permissions, and secure error logging.
- Plan migration of current SQLite data to PostgreSQL on a **staging copy**, including uploaded media and correct sequences. This package **does not migrate your data**. Never point migration commands at your live SQLite database to transfer it to PostgreSQL.

## Deploy using a Linux host — outline, NOT a ready-to-run public launch

1. Upload **source code only** to a private repository. Check `git status` and `git ls-files` for tracked secrets/database/media. `.gitignore` does not untrack committed files. Do not upload `db.sqlite3`, `.env`, backups, media or actual payment data.
2. Configure the private hosting environment variables shown in `production.env.example`. Set `DJANGO_SETTINGS_MODULE=config.settings_production`.
3. Generate a new random production-only `SMARTMART_SECRET_KEY`, e.g. using `python -c "import secrets; print(secrets.token_urlsafe(64))"`. Store only in the hosting provider's private environment controls; **do not send it through chat or commit it**.
4. Install the app requirements + `deployment_stage10d/requirements-production.txt` in a dedicated production virtual environment. Run a pinned dependencies/security review first.
5. Configure managed PostgreSQL via `DATABASE_URL`. The production settings *reject* SQLite. Provide a persistent, private `SMARTMART_MEDIA_ROOT` absolute path or adapt the media storage to a suitable cloud backend.
6. Configure the domain, HTTPS reverse proxy, and a verified TLS certificate. Keep `SMARTMART_TRUST_PROXY_HTTPS=0` unless your proxy overwrites untrusted forwarded headers. Incorrect configuration can enable spoofing or loops.
7. Set `SMARTMART_ALLOWED_HOSTS` to comma-separated hostnames, e.g. `store.example.com,www.store.example.com`. Set `SMARTMART_CSRF_TRUSTED_ORIGINS` to the actual HTTPS origins.
8. On the **staging** environment first, with production settings and a staging PostgreSQL database, run:

   ```bash
   python manage.py check --deploy
   python manage.py migrate --noinput
   python manage.py collectstatic --noinput
   ```

   **Do not run** `python manage.py test` directly against your live production database. Tests create/delete a test database and can require broad database privileges. Run tests in CI or a staging environment instead.
9. On a Linux host use a production WSGI/ASGI server; an example WSGI command is `gunicorn config.wsgi:application --bind 127.0.0.1:8000 --workers 3` behind your trusted TLS reverse proxy. Your hosting provider may require a different startup command. **Do not** expose `runserver` publicly.
10. Perform staging end-to-end tests for role-based access, price import, POS sale + refund, stock receiving/transfers, payment verification, backups and disaster recovery.
11. Launch only after staging passes and a separate operator confirms production readiness. Keep `SMARTMART_HSTS_SECONDS=0` until HTTPS is proven. Roll out HSTS cautiously (for example, 300 seconds first) before any long durations. Don't preload or include subdomains until you control HTTPS for all affected hosts.

## Environment variables

See `deployment_stage10d/production.env.example` for placeholders. It is an EXAMPLE ONLY; do not fill it with real secrets inside a Git-tracked file. Configure the actual environment in your host's secret manager.

- `SMARTMART_SECRET_KEY`: new long unique production secret.
- `SMARTMART_ALLOWED_HOSTS`: explicit hostname list; no `*`.
- `SMARTMART_CSRF_TRUSTED_ORIGINS`: HTTPS origins.
- `DATABASE_URL`: managed PostgreSQL URL (TLS required).
- `SMARTMART_MEDIA_ROOT`: absolute persistent private filesystem media directory, if your host has persistent disks. Cloud object storage requires a different storage backend.
- `SMARTMART_TRUST_PROXY_HTTPS`: `0` by default; set to `1` only for a trusted sanitizing proxy.
- `SMARTMART_HSTS_SECONDS`: initially `0`, then raise cautiously after HTTPS is verified.

## Run a final security inspection

After hosting and environment provisioning:

```bash
python smartmart_deployment_doctor.py --production
python manage.py check --deploy --settings=config.settings_production
```

Security system checks are a **baseline**, not a complete penetration test or payment-provider compliance assessment. Django may issue an HSTS-related warning intentionally while initial HSTS rollout is disabled.

## Backups

Your current `smartmart_backup.py` only backs up the local **SQLite** database (and local media). Once on PostgreSQL, configure proper PostgreSQL/managed backups and regularly test restoration. Do not mistake a SQLite backup for PostgreSQL coverage.

## Support references

- Django 5.2 Deployment Checklist: https://docs.djangoproject.com/en/5.2/howto/deployment/checklist/
- Django 5.2 How to Deploy: https://docs.djangoproject.com/en/5.2/howto/deployment/
