"""Safely installs the SmartMart ERP Stage 2 portal into an existing Django project.

Run this script from the same folder as manage.py with the project's .venv active.
Does not overwrite Django's auth tables or delete any existing data.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
import re
import shutil
import subprocess
import sys


BASE = Path(__file__).resolve().parent
SETTINGS = BASE / "config" / "settings.py"
URLS = BASE / "config" / "urls.py"


def fail(message: str) -> None:
    print(f"\nERROR: {message}")
    sys.exit(1)


def run(*args: str) -> None:
    command = [sys.executable, str(BASE / "manage.py"), *args]
    print("\nRUNNING:", " ".join(command), flush=True)
    result = subprocess.run(command, cwd=BASE, check=False)
    if result.returncode:
        fail(f"The command {' '.join(args)} failed (exit {result.returncode}). Review the error above. Your backup is safe.")


def main() -> None:
    print("SMARTMART ERP - STAGE 2 PORTALS")
    if not (BASE / "manage.py").is_file():
        fail("manage.py was not found. Extract the ZIP in your SmartMartERP project root.")
    if not SETTINGS.is_file() or not URLS.is_file():
        fail("Expected config/settings.py and config/urls.py. Do not run this in CampusLMS.")
    for required in ["models.py", "views.py", "urls.py", "admin.py", "forms.py"]:
        if not (BASE / "core" / required).is_file():
            fail(f"Missing core/{required}. Please extract the whole ZIP first.")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    backup = BASE / "SmartMart_Stage2_Backups" / timestamp
    (backup / "config").mkdir(parents=True)
    shutil.copy2(SETTINGS, backup / "config" / "settings.py")
    shutil.copy2(URLS, backup / "config" / "urls.py")
    if (BASE / "db.sqlite3").exists():
        shutil.copy2(BASE / "db.sqlite3", backup / "db.sqlite3")
    print("Backup created:", backup)

    settings = SETTINGS.read_text(encoding="utf-8")
    app_string = '"core.apps.CoreConfig"'
    if "core.apps.CoreConfig" not in settings:
        match = re.search(r"(?m)^(\s*INSTALLED_APPS\s*=\s*\[\s*\n)", settings)
        if not match:
            fail("Could not locate INSTALLED_APPS = [ in settings.py. Restore the backup and inspect manually.")
        settings = settings[:match.end()] + f"    {app_string},\n" + settings[match.end():]
    if "SMARTMART_STAGE2_LOGIN" not in settings:
        settings += (
            "\n\n# SMARTMART_STAGE2_LOGIN: portal authentication redirects\n"
            'LOGIN_URL = "core:login"\n'
            'LOGIN_REDIRECT_URL = "core:dashboard"\n'
            'LOGOUT_REDIRECT_URL = "core:home"\n'
        )
    SETTINGS.write_text(settings, encoding="utf-8")

    urls = URLS.read_text(encoding="utf-8")
    if 'include("core.urls")' not in urls and "include('core.urls')" not in urls:
        match = re.search(r"(?m)^from django\.urls import ([^\n]+)$", urls)
        if not match:
            fail("Could not find 'from django.urls import path' in config/urls.py. Use the saved backup to restore settings if needed.")
        imports = match.group(1).strip()
        if "include" not in re.findall(r"[A-Za-z_]+", imports):
            imports = imports + ", include"
        urls = urls[:match.start()] + f"from django.urls import {imports}" + urls[match.end():]
        match = re.search(r"(?m)^(\s*urlpatterns\s*=\s*\[\s*\n)", urls)
        if not match:
            fail("Could not locate urlpatterns = [ in config/urls.py. Files have been backed up.")
        urls = urls[:match.end()] + '    path("", include("core.urls")),\n' + urls[match.end():]
        URLS.write_text(urls, encoding="utf-8")

    print("Configuration updated (existing app routes preserved).")
    run("check")
    run("makemigrations", "core", "--noinput")
    run("migrate", "--noinput")
    run("test", "core")
    print("\nSUCCESS: SmartMart Stage 2 checks and tests passed.")
    print("Next: python manage.py createsuperuser  (if you have not done so)")
    print("Then: python manage.py runserver 8002")
    print("Open: http://127.0.0.1:8002/")
    print("Backup:", backup)


if __name__ == "__main__":
    main()
