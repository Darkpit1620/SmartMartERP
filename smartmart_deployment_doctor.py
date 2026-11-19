"""Read-only SmartMart ERP deployment preparation checks.

Run locally:  python smartmart_deployment_doctor.py
On provisioned host: python smartmart_deployment_doctor.py --production
No secrets or database rows are printed or changed.
"""
from pathlib import Path
import argparse
import os
import subprocess
import sys

ROOT = Path(__file__).resolve().parent


def report(label, good, fix):
    print(("[PASS] " if good else "[ACTION] ") + label)
    if not good:
        print("         " + fix)
    return bool(good)


def main():
    parser = argparse.ArgumentParser(description="Read-only SmartMart deployment preparation")
    parser.add_argument("--production", action="store_true", help="Run Django production checks against configured hosting environment")
    args = parser.parse_args()
    print("SMARTMART ERP / STAGE 10D — DEPLOYMENT PREPARATION\n")
    valid = True
    valid &= report("Production-only settings exist", (ROOT / "config/settings_production.py").is_file(), "Run python install_smartmart_stage10d.py")
    valid &= report("Private SQLite backup utility is available", (ROOT / "smartmart_backup.py").is_file(), "Install Stage 9 and back up before deployment.")
    valid &= report(".gitignore exists", (ROOT / ".gitignore").is_file(), "Add rules to protect databases, credentials, uploads, and backup files.")
    valid &= report("Existing Django project found", (ROOT / "manage.py").is_file(), "Run inside your SmartMartERP folder.")

    required = ["SMARTMART_SECRET_KEY", "SMARTMART_ALLOWED_HOSTS", "SMARTMART_CSRF_TRUSTED_ORIGINS", "DATABASE_URL", "SMARTMART_MEDIA_ROOT"]
    ready = all(os.environ.get(k, "").strip() for k in required)
    report("Production environment secrets and host settings are configured", ready, "Set these on the hosting provider (do not type them into chat or commit them to GitHub).")
    if not args.production:
        print("\nLocal preparation check finished. Existing localhost settings have NOT been changed.")
        print("Production readiness is NOT confirmed; provision HTTPS hosting and PostgreSQL first.")
        return 0 if valid else 1
    if not ready or not valid:
        print("\nSTOP: Missing configuration. No production Django check was attempted.")
        return 1
    print("\nRunning Django's production deployment checks (read-only):")
    env = os.environ.copy()
    env["DJANGO_SETTINGS_MODULE"] = "config.settings_production"
    p = subprocess.run([sys.executable, "manage.py", "check", "--deploy"], cwd=ROOT, env=env, check=False)
    if p.returncode:
        print("\nDeployment checks failed. Do not go live.")
        return p.returncode
    print("\nReview EVERY warning above. HSTS intentionally remains disabled until HTTPS is verified.")
    print("This does not certify payment processing, backup restoration, or external security.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
