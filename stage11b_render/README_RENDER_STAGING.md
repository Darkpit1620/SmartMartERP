# SmartMart ERP — Stage 11B: Render staging deployment

This is a **manual staging deployment guide**, not an automated paid-service purchase or a public production launch. Your existing `config/settings.py`, SQLite data, and local `runserver 8002` remain untouched.

## 1. Install and verify on Windows

Run from the **existing SmartMartERP** directory:

```powershell
Expand-Archive -LiteralPath "$env:USERPROFILE\Downloads\SmartMartERP_Stage11B_Render_Staging.zip" -DestinationPath . -Force
python install_smartmart_stage11b.py
python smartmart_stage11b_preflight.py
python manage.py test --noinput
```

The installer adds `config/settings_render_staging.py`, two Render shell scripts, `.python-version` if absent, and safe `.gitignore` entries. It first calls the existing Stage 9 verified backup. It does **not** create a new user or modify business data.

## 2. Confirm GitHub is ready

```powershell
git remote -v
git status --short
python smartmart_stage11b_preflight.py
```

If `git remote -v` shows no remote, complete GitHub publishing (Stage 11A) before deploying. Review your staged paths manually for secrets. Do not force-add `.env`, database, backups, media or `.venv`.

To commit these **new code files** after inspection:

```powershell
git add config/settings_render_staging.py render_staging_build.sh render_staging_start.sh .python-version .gitignore
git diff --cached --name-only
git commit -m "Prepare isolated Render staging deployment"
git push origin main
```

If `.python-version` already had a different value, the installer preserves it. Only add the file if it exists; if Git says no changes were added, there is nothing new to commit. Ensure no real secrets are hardcoded in other already-tracked code.

## 3. Create a separate staging PostgreSQL database on Render

1. Open https://dashboard.render.com/ and sign in.
2. Select **New → Postgres**. Use a separate name like `smartmart-staging-db` and select a region near your web service.
3. Select a plan intentionally. **Free PostgreSQL expires after 30 days and has no managed backups**; do not use it for real customer or financial records. Paid PostgreSQL is recommended for lasting staging.
4. After creation, locate the **internal database URL**. Keep this URL private; do **not** put it in Git or send it through chat.

## 4. Create a staging web service

1. In Render, select **New → Web Service** and connect your **private GitHub repository** `SmartMartERP`.
2. Choose Python runtime and the Git branch containing your Stage 11B files (usually `main`).
3. Give it a staging-only name (for example, `smartmart-staging-unique-name`), select the **same region as PostgreSQL**, and turn off auto-deploy until you have tested the setup if you want full control.
4. Choose a **paid web compute plan** for this setup: Render persistent disks are not supported on free web services. Review the provider's charges before creating paid resources.
5. Under Advanced, attach a persistent disk with **mount path `/var/data`**. Only that directory is persistent; uploaded files will go to `/var/data/media`.
6. Enter these commands:

   **Build command**:
   ```bash
   bash render_staging_build.sh
   ```

   **Pre-deploy command** (paid web plan):
   ```bash
   python manage.py migrate --noinput --settings=config.settings_render_staging
   ```

   **Start command**:
   ```bash
   bash render_staging_start.sh
   ```

7. Add the environment variables shown below. Then create the Web Service. Render will provide a `.onrender.com` address and TLS certificate.

## 5. Required environment variables (Render Dashboard only)

| Name | Value / how to set it |
|---|---|
| `DJANGO_SETTINGS_MODULE` | `config.settings_render_staging` |
| `PYTHON_VERSION` | `3.12.10` (or align with your existing `.python-version`) |
| `DATABASE_URL` | Staging PostgreSQL **internal connection URL** (secret) |
| `SMARTMART_SECRET_KEY` | Unique random secret, **at least 50 characters**, generated in secure environment settings |
| `SMARTMART_ALLOWED_HOSTS` | The exact `your-service.onrender.com` hostname, without `https://` |
| `SMARTMART_CSRF_TRUSTED_ORIGINS` | `https://your-service.onrender.com` |
| `SMARTMART_MEDIA_ROOT` | `/var/data/media` (the disk is mounted at `/var/data`) |
| `SMARTMART_TRUST_PROXY_HTTPS` | `0` |
| `SMARTMART_HSTS_SECONDS` | `0` initially |

Replace `your-service` with your *actual* Render web service hostname. NEVER copy the example hostname as-is. Set secrets using Render environment-variable controls. Generate a new production-like test secret, not the existing Django development secret.

The `settings_render_staging.py` module imports Stage 10D's production settings and disables Django's second HTTP→HTTPS redirect. Render's edge redirects HTTP to HTTPS already. This avoids redirect loops while retaining secure session and CSRF cookies. `check --deploy` will therefore still show **W008** (and W004 until HSTS is enabled), which must be reviewed in the hosting context rather than silently suppressed.

## 6. First migration and admin account

The **pre-deploy command** creates the PostgreSQL schema. It does NOT import your SQLite database. This is deliberate. Your staging system starts with an empty database.

After successful deployment, use the Render service's **Shell** (available with a suitable paid plan) to create a NEW staging administrator:

```bash
python manage.py createsuperuser --settings=config.settings_render_staging
```

Use entirely new credentials. Never import your local admin password, real customers or real payment references. Use test-only branches/products/employees to validate access controls and stock movements.

## 7. Staging smoke checks

1. Open the exact Render HTTPS URL (your public staging homepage).
2. Sign in with the **new** staging admin account; open the Administrator Dashboard.
3. Create a test branch and eight sample products or run the training setup command if available.
4. Test login and role restrictions, retail POS, wholesale checkout, purchasing, branch transfer and finance.
5. Refresh pages and restart the service. Confirm PostgreSQL records persist and uploaded media is retained on the disk, if your app uses uploads.
6. In the Render shell run `python manage.py check --deploy --settings=config.settings_render_staging`; review warnings for proxy-managed redirects and HSTS. Verify backup and restore procedures for the **PostgreSQL** database; the existing SQLite backup utility does not cover it.

**Security**: This web-service URL is on the public internet. Do not use real customers, real payment credentials, or business-sensitive data during staging. Restrict access further if confidential testing is needed. A private GitHub repository does NOT make the deployed site private.

## 8. Troubleshooting

- **Build fails `ModuleNotFoundError`**: inspect Render build logs. Your original project may require extra Python dependencies; add reviewed packages to `requirements.txt` and redeploy.
- **Build fails `ImproperlyConfigured`**: check the missing env vars, Render hostname, database URL and `SMARTMART_MEDIA_ROOT`.
- **`DisallowedHost`**: use the exact Render hostname in `SMARTMART_ALLOWED_HOSTS`.
- **CSRF verification failed**: use the exact HTTPS service URL in `SMARTMART_CSRF_TRUSTED_ORIGINS` and check cookies.
- **DB connection failure**: use PostgreSQL internal URL with TLS support; ensure DB is live and in the same region.
- **Static styles missing**: check the build log for successful `collectstatic` and WhiteNoise installation.
- **Uploaded files disappear**: confirm a paid persistent disk is mounted at `/var/data` and uploads use `/var/data/media`.
- **You see Django's HSTS/redirect warnings**: on Render the HTTPS edge redirects requests; review the documented exception rather than blindly setting `SECURE_SSL_REDIRECT=True` behind the proxy.
- **No GitHub repository yet**: complete Stage 11A first; the installer does not connect to GitHub.

## 9. What this package explicitly does NOT do

It does not purchase hosting, create a Render account, create a database, push code, transfer live SQLite records, integrate real M-Pesa/cards, configure KRA eTIMS, or certify production readiness. Proceed to live deployment only after real payment verification, secure media authorization, tax compliance, incident monitoring and backup/restore tests.

## Authoritative references

- Render Django deployment: https://render.com/docs/deploy-django
- Render web services: https://render.com/docs/web-services
- Render persistent disks: https://render.com/docs/disks
- Render free plan limitations: https://render.com/docs/free
- Django 5.2 deployment checklist: https://docs.djangoproject.com/en/5.2/howto/deployment/checklist/
