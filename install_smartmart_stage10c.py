"""SmartMart Stage 10C: add isolated integration tests and read-only admin testing hub.

Run from SmartMartERP root: python install_smartmart_stage10c.py
No migrations or seed data; tests create a temporary, automatically destroyed DB.
"""
from __future__ import annotations

from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
SETTINGS = ROOT / "config" / "settings.py"
URLS = ROOT / "config" / "urls.py"
ADMIN = ROOT / "core" / "templates" / "core" / "admin_portal.html"
APP = ROOT / "transaction_checks"


def fail(message):
    raise SystemExit("\nSTAGE 10C STOPPED: " + message)


def plan_changes():
    required = [
        ROOT / "manage.py", SETTINGS, URLS, ADMIN,
        ROOT / "smartmart_backup.py",
        ROOT / "core" / "models.py",
        ROOT / "inventory" / "models.py", ROOT / "inventory" / "services.py",
        ROOT / "pos" / "models.py", ROOT / "pos" / "services.py",
        ROOT / "trading" / "models.py", ROOT / "trading" / "services.py",
        ROOT / "transfers" / "models.py", ROOT / "transfers" / "services.py",
        ROOT / "finance_ops" / "models.py", ROOT / "finance_ops" / "services.py",
        APP / "apps.py", APP / "urls.py", APP / "views.py", APP / "tests.py",
        APP / "templates" / "transaction_checks" / "overview.html",
    ]
    missing = [str(p.relative_to(ROOT)) for p in required if not p.is_file()]
    if missing:
        fail("Missing files: " + ", ".join(missing) + ". Extract the ZIP in your SmartMartERP root folder.")
    original = {p: p.read_text(encoding="utf-8") for p in (SETTINGS, URLS, ADMIN)}

    settings = original[SETTINGS]
    needed_apps = (
        "core.apps.CoreConfig", "inventory.apps.InventoryConfig",
        "pos.apps.PosConfig", "trading.apps.TradingConfig",
        "transfers.apps.TransfersConfig", "finance_ops.apps.FinanceOpsConfig",
    )
    if any(name not in settings for name in needed_apps):
        fail("Expected core, inventory, POS, trading, transfers and finance apps to be installed. No files changed.")
    if "transaction_checks.apps.TransactionChecksConfig" not in settings:
        match = re.search(r"(?m)^\s*INSTALLED_APPS\s*=\s*\[\s*\n", settings)
        if not match:
            fail("Cannot identify INSTALLED_APPS. No changes made.")
        settings = (settings[:match.end()]
                    + '    "transaction_checks.apps.TransactionChecksConfig",\n'
                    + settings[match.end():])

    urls = original[URLS]
    if not re.search(r"\binclude\s*\(\s*['\"]transaction_checks\.urls['\"]\s*\)", urls):
        imports = re.search(r"(?m)^from django\.urls import ([^\n]+)$", urls)
        if not imports:
            fail("Cannot safely locate django.urls imports. No files changed.")
        items = [part.strip() for part in imports.group(1).split(",")]
        for name in ("path", "include"):
            if name not in items:
                items.append(name)
        urls = (urls[:imports.start()]
                + "from django.urls import " + ", ".join(items)
                + urls[imports.end():])
        location = re.search(r"(?m)^\s*urlpatterns\s*=\s*\[\s*\n", urls)
        if not location:
            fail("Cannot locate urlpatterns. No changes made.")
        urls = (urls[:location.end()]
                + '    path("transaction-tests/", include("transaction_checks.urls")),\n'
                + urls[location.end():])

    admin = original[ADMIN]
    if "SMARTMART_STAGE10C_TRANSACTION_CARD" not in admin:
        where = admin.rfind("{% endblock %}")
        if where < 0:
            fail("Cannot safely locate the admin workspace template block. No files changed.")
        section = (
            '\n<!-- SMARTMART_STAGE10C_TRANSACTION_CARD -->\n'
            '<section class="wrap" style="padding:12px 0 36px">'
            '<div class="profile-strip"><div><strong>Full Transaction Testing</strong>'
            '<p>Verify retail and wholesale sales, goods receiving, branch transfers and finance.</p>'
            '</div><a class="button button-primary" href="{% url \'transaction_checks:overview\' %}">Open transaction checklist →</a>'
            '</div></section>\n'
        )
        admin = admin[:where] + section + admin[where:]

    return original, {SETTINGS: settings, URLS: urls, ADMIN: admin}


def run(*arguments):
    print("RUNNING: python manage.py " + " ".join(arguments), flush=True)
    result = subprocess.run([sys.executable, str(ROOT / "manage.py"), *arguments], cwd=ROOT, check=False)
    if result.returncode:
        raise RuntimeError("Django check or test failed; read the error above.")


def install():
    print("SMARTMART ERP STAGE 10C — FULL TRANSACTION TESTING", flush=True)
    original, updates = plan_changes()
    try:
        from smartmart_backup import create_backup
        backup = create_backup()
    except Exception as exc:
        fail("Database backup failed. No configuration files were changed: " + str(exc))
    print("VERIFIED PRIVATE BACKUP:", backup, flush=True)
    for path, content in original.items():
        target = backup / "preinstall_files" / path.relative_to(ROOT)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    changed = []
    try:
        for path, content in updates.items():
            if content != original[path]:
                path.write_text(content, encoding="utf-8")
                changed.append(path)
        run("check")
        run("test", "transaction_checks", "--noinput")
    except Exception as exc:
        for path in reversed(changed):
            path.write_text(original[path], encoding="utf-8")
        fail(str(exc) + " Original configuration files have been restored. Your database was not reset.")
    print("\nSTAGE 10C INSTALLED SUCCESSFULLY")
    print("No inventory, payment, branch or employee records were created by the test suite.")
    print("Open Admin Workspace > Full Transaction Testing after starting the server.")
    print("Run full suite: python manage.py test --noinput")
    print("Run live read-only audit: python manage.py smartmart_audit")
    print("Backup:", backup)


if __name__ == "__main__":
    install()
