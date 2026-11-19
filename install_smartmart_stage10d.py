"""Install non-invasive production preparation files into an existing SmartMartERP.

Does NOT change config/settings.py, URLs, authentication, migrations, inventory,
stock or POS data. Creates a verified private SQLite backup before modifying
.gitignore or adding config/settings_production.py.
"""
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
MAIN = ROOT / "config" / "settings.py"
TARGET = ROOT / "config" / "settings_production.py"
TEMPLATE = ROOT / "deployment_stage10d" / "settings_production.template.py"
GITIGNORE = ROOT / ".gitignore"

IGNORE_TAG = "# SMARTMART_STAGE10D_DEPLOYMENT_IGNORE"
IGNORE_LINES = '''\n# SMARTMART_STAGE10D_DEPLOYMENT_IGNORE\n/db.sqlite3\n/db.sqlite3-*\n/staticfiles/\n/media/\n/.env\n/.env.*\n*.pem\n*.key\n/SmartMart_*Backups/\n/SmartMart_Stage*_Backups/\n/.venv/\n__pycache__/\n*.py[cod]\n'''


def fail(s):
    raise SystemExit("\nSTAGE 10D STOPPED: " + s)


def main():
    print("SMARTMART ERP — STAGE 10D: SECURE DEPLOYMENT PREPARATION", flush=True)
    required = [ROOT / "manage.py", MAIN, TEMPLATE, ROOT / "smartmart_backup.py"]
    if any(not f.is_file() for f in required):
        fail("Missing required project or package file. Extract Stage 10D ZIP into the SmartMartERP folder, after Stage 9.")
    text = MAIN.read_text(encoding="utf-8")
    if "core.apps.CoreConfig" not in text or "operations.apps.OperationsConfig" not in text:
        fail("Expected existing SmartMart Core and Stage 9 Operations apps in settings.py. No changes made.")
    prod_code = TEMPLATE.read_text(encoding="utf-8")
    if TARGET.exists() and TARGET.read_text(encoding="utf-8") != prod_code:
        fail("Existing customized config/settings_production.py detected. No files changed. Review before replacing.")
    previous_ignore = GITIGNORE.read_text(encoding="utf-8") if GITIGNORE.exists() else None
    new_ignore = previous_ignore or ""
    if IGNORE_TAG not in new_ignore:
        new_ignore = new_ignore.rstrip("\n") + "\n" + IGNORE_LINES
    needs_change = not TARGET.exists() or (previous_ignore or "") != new_ignore
    if not needs_change:
        print("Already installed. No files changed.")
        return 0
    try:
        from smartmart_backup import create_backup
        backup = create_backup()
    except Exception as exc:
        fail("Verified backup failed; NO files were changed: " + str(exc))
    print("VERIFIED PRIVATE BACKUP:", backup, flush=True)
    pre = backup / "preinstall_files"
    if previous_ignore is not None:
        destination = pre / ".gitignore"
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(previous_ignore, encoding="utf-8")
    original_prod = TARGET.read_text(encoding="utf-8") if TARGET.exists() else None
    try:
        if original_prod is None:
            TARGET.write_text(prod_code, encoding="utf-8")
        if (previous_ignore or "") != new_ignore:
            GITIGNORE.write_text(new_ignore, encoding="utf-8")
        result = subprocess.run([sys.executable, str(ROOT / "manage.py"), "check"], cwd=ROOT, check=False)
        if result.returncode:
            raise RuntimeError("Local Django check failed. See output above.")
    except Exception as e:
        if original_prod is None and TARGET.exists():
            TARGET.unlink()
        if previous_ignore is None:
            if GITIGNORE.exists():
                GITIGNORE.unlink()
        else:
            GITIGNORE.write_text(previous_ignore, encoding="utf-8")
        fail(str(e) + " Original configuration was restored. Database remains untouched.")
    print("\nSTAGE 10D PREPARATION INSTALLED SUCCESSFULLY")
    print("Local development settings and existing records were NOT modified.")
    print("Next: python smartmart_deployment_doctor.py")
    print("Read deployment_stage10d/README_DEPLOYMENT.md before hosting.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
