"""SmartMart ERP Stage 3B: safe installation of the ready-made supermarket catalogue.

Run in SmartMartERP next to manage.py after extracting the archive.
"""
from datetime import datetime
from pathlib import Path
import re
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
SETTINGS = ROOT / "config" / "settings.py"
URLS = ROOT / "config" / "urls.py"
BASE = ROOT / "core" / "templates" / "core" / "base.html"
ADMIN = ROOT / "core" / "templates" / "core" / "admin_portal.html"


def die(message):
    raise SystemExit("\nSTOPPED SAFELY: " + message)


def django(*args):
    print("\nRunning:", "python manage.py", " ".join(args), flush=True)
    if subprocess.run([sys.executable, str(ROOT / "manage.py"), *args], cwd=ROOT).returncode != 0:
        die("Django reported an error above. Original backup remains available. Resolve the error before rerunning.")


def create_backup(paths):
    destination = ROOT / "SmartMart_Bulk_Backups" / datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    for path in paths:
        if path.is_file():
            output = destination / path.relative_to(ROOT)
            output.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, output)
    db = ROOT / "db.sqlite3"
    if db.is_file():
        destination.mkdir(parents=True, exist_ok=True)
        shutil.copy2(db, destination / "db.sqlite3")
    print("Backup stored in:", destination)
    return destination


def main():
    print("\nSMARTMART ERP — STAGE 3B — BULK SUPERMARKET CATALOGUE")
    mandatory = [
        ROOT / "manage.py", SETTINGS, URLS, BASE, ADMIN,
        ROOT / "core" / "models.py", ROOT / "inventory" / "models.py",
        ROOT / "smartmart_bulk" / "apps.py", ROOT / "smartmart_bulk" / "urls.py",
        ROOT / "smartmart_bulk" / "data" / "smartmart_bulk_catalogue.csv",
    ]
    absent = [str(path.relative_to(ROOT)) for path in mandatory if not path.is_file()]
    if absent:
        die("Expected Stage 2/3 files are missing: " + ", ".join(absent) + ". Check your current project folder.")

    old = {path: path.read_text(encoding="utf-8") for path in [SETTINGS, URLS, BASE, ADMIN]}
    if 'inventory.apps.InventoryConfig' not in old[SETTINGS]:
        die("Stage 3 Inventory is not registered. Install SmartMart Stage 3 first.")
    if "class Product(" not in (ROOT / "inventory" / "models.py").read_text(encoding="utf-8"):
        die("Existing inventory.Product model not found. No project files changed.")
    if "INSTALLED_APPS" not in old[SETTINGS] or "urlpatterns" not in old[URLS]:
        die("Could not locate Django settings or URL configuration.")
    navigation = '<a class="nav-link" href="{% url \'core:dashboard\' %}">My workspace</a>'
    if navigation not in old[BASE] and "SMARTMART_BULK_NAV" not in old[BASE]:
        die("The shared navigation is customized. Installer will not guess where to insert the catalogue link.")
    if '<div class="profile-strip">' not in old[ADMIN] and "SMARTMART_BULK_ADMIN" not in old[ADMIN]:
        die("The administrator workspace layout has changed. Installer will not overwrite it.")

    destination = create_backup(old)

    settings = old[SETTINGS]
    if "smartmart_bulk.apps.SmartmartBulkConfig" not in settings:
        m = re.search(r"(?m)^\s*INSTALLED_APPS\s*=\s*\[\s*\n", settings)
        if not m:
            die("Could not find INSTALLED_APPS list. Backup is safe; nothing else modified.")
        settings = settings[:m.end()] + '    "smartmart_bulk.apps.SmartmartBulkConfig",\n' + settings[m.end():]
    SETTINGS.write_text(settings, encoding="utf-8")

    urls = old[URLS]
    if 'include("smartmart_bulk.urls")' not in urls and "include('smartmart_bulk.urls')" not in urls:
        m = re.search(r"(?m)^from django\.urls import ([^\n]+)$", urls)
        if not m:
            die("Django URLs import not found. See backup.")
        names = m.group(1)
        if "include" not in names.split(",") and "include" not in [x.strip() for x in names.split(",")]:
            urls = urls[:m.start()] + f"from django.urls import {names.strip()}, include" + urls[m.end():]
        m = re.search(r"(?m)^\s*urlpatterns\s*=\s*\[\s*\n", urls)
        if not m:
            die("urlpatterns list missing. See backup.")
        urls = urls[:m.end()] + '    path("catalogue/", include("smartmart_bulk.urls")),\n' + urls[m.end():]
    URLS.write_text(urls, encoding="utf-8")

    base = old[BASE]
    if "SMARTMART_BULK_NAV" not in base:
        base = base.replace(navigation, navigation + '\n          <!-- SMARTMART_BULK_NAV -->\n          <a class="nav-link" href="{% url \'smartmart_bulk:browse\' %}">Shop catalogue</a>', 1)
    if "SMARTMART_BULK_CSS" not in base:
        if "</head>" not in base:
            die("Template has no closing head tag; CSS cannot be added safely.")
        base = base.replace("</head>",
            "  <!-- SMARTMART_BULK_CSS -->\n  <link rel=\"stylesheet\" href=\"{% static 'smartmart_bulk/css/catalogue.css' %}\">\n</head>", 1)
    BASE.write_text(base, encoding="utf-8")

    admin = old[ADMIN]
    if "SMARTMART_BULK_ADMIN" not in admin:
        fragment = ('<!-- SMARTMART_BULK_ADMIN -->\n'
                    '<div class="dashboard-cards" style="margin-top:18px">'
                    '<section class="dashboard-card"><div class="card-icon green">▦</div>'
                    '<h3>Full Supermarket Catalogue</h3>'
                    '<p>Browse groceries, electronics, clothing, household products and 49 departments.</p>'
                    '<a class="dashboard-card-link" href="{% url \'smartmart_bulk:browse\' %}">Browse all departments →</a>'
                    '</section></div>\n')
        admin = admin.replace('<div class="profile-strip">', fragment + '<div class="profile-strip">', 1)
    ADMIN.write_text(admin, encoding="utf-8")

    django("check")
    django("test", "smartmart_bulk", "--noinput")
    django("import_bulk_catalogue", "--dry-run")
    django("import_bulk_catalogue")
    print("\nSUCCESS: Large supermarket catalogue installed.")
    print("Start your site: python manage.py runserver 8002")
    print("Sign in as admin/approved staff and choose SHOP CATALOGUE in the navigation bar.")
    print("All imported prices are pending verification. No branch stock was fabricated.")
    print("Backup:", destination)


if __name__ == "__main__":
    main()
