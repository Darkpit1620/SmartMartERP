"""Install SmartMart Stage 3 from the existing SmartMartERP folder (where manage.py lives)."""
from datetime import datetime
from pathlib import Path
import re
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
SETTINGS = ROOT / "config" / "settings.py"
URLS = ROOT / "config" / "urls.py"
BASE_HTML = ROOT / "core" / "templates" / "core" / "base.html"
ADMIN_HTML = ROOT / "core" / "templates" / "core" / "admin_portal.html"
STAFF_HTML = ROOT / "core" / "templates" / "core" / "staff_portal.html"


def stop(message):
    raise SystemExit("\nERROR: " + message)


def run(*args):
    command = [sys.executable, str(ROOT / "manage.py"), *args]
    print("\nRunning:", " ".join(command), flush=True)
    if subprocess.run(command, cwd=ROOT).returncode:
        stop("Django command failed. Correct the error above before continuing. Your backup is preserved.")


def backup(files):
    target = ROOT / "SmartMart_Stage3_Backups" / datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    for path in files:
        if path.exists():
            output = target / path.relative_to(ROOT)
            output.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, output)
    database = ROOT / "db.sqlite3"
    if database.exists():
        target.mkdir(parents=True, exist_ok=True)
        shutil.copy2(database, target / database.name)
    print("Backup:", target)
    return target


def main():
    print("\nSMARTMART ERP — STAGE 3: PRODUCTS AND STOCK")
    expected = [ROOT / "manage.py", SETTINGS, URLS, BASE_HTML, ADMIN_HTML, STAFF_HTML,
                ROOT / "core" / "models.py", ROOT / "inventory" / "models.py", ROOT / "inventory" / "urls.py"]
    missing = [str(f.relative_to(ROOT)) for f in expected if not f.is_file()]
    if missing:
        stop("Missing files: " + ", ".join(missing) + ". Run from SmartMartERP, not CampusLMS.")
    core_model = (ROOT / "core" / "models.py").read_text(encoding="utf-8")
    if "class Branch(" not in core_model or "class StaffProfile(" not in core_model:
        stop("The expected Stage 2 Branch/StaffProfile models are missing. No changes made.")
    source = {p: p.read_text(encoding="utf-8") for p in [SETTINGS, URLS, BASE_HTML, ADMIN_HTML, STAFF_HTML]}
    for p, anchor in [(SETTINGS, "INSTALLED_APPS"), (URLS, "urlpatterns"),
                      (BASE_HTML, "</head>"), (ADMIN_HTML, 'class="profile-strip"'), (STAFF_HTML, 'class="profile-strip"')]:
        if anchor not in source[p]:
            stop(f"Expected anchor {anchor!r} missing in {p.relative_to(ROOT)}. No changes made.")
    prior = backup(source)
    print("Updating site navigation and workspace cards...")

    settings = source[SETTINGS]
    if "inventory.apps.InventoryConfig" not in settings:
        match = re.search(r"(?m)^\s*INSTALLED_APPS\s*=\s*\[\s*\n", settings)
        if not match:
            stop("Cannot find INSTALLED_APPS list. Restore files from the backup.")
        settings = settings[:match.end()] + '    "inventory.apps.InventoryConfig",\n' + settings[match.end():]
    SETTINGS.write_text(settings, encoding="utf-8")

    urls = source[URLS]
    if 'include("inventory.urls")' not in urls and "include('inventory.urls')" not in urls:
        m = re.search(r"(?m)^from django\.urls import ([^\n]+)$", urls)
        if not m:
            stop("Cannot locate django.urls import. Review backup before continuing.")
        imports = m.group(1).strip()
        if "include" not in re.findall(r"\w+", imports):
            imports += ", include"
        urls = urls[:m.start()] + f"from django.urls import {imports}" + urls[m.end():]
        m = re.search(r"(?m)^\s*urlpatterns\s*=\s*\[\s*\n", urls)
        if not m:
            stop("Cannot find urlpatterns list. Review backup before continuing.")
        urls = urls[:m.end()] + '    path("inventory/", include("inventory.urls")),\n' + urls[m.end():]
    URLS.write_text(urls, encoding="utf-8")

    base = source[BASE_HTML]
    if "SMARTMART_STAGE3_CSS" not in base:
        base = base.replace("</head>", "  <!-- SMARTMART_STAGE3_CSS -->\n  <link rel=\"stylesheet\" href=\"{% static 'inventory/css/inventory.css' %}\">\n</head>", 1)
    if "SMARTMART_STAGE3_NAV" not in base:
        anchor = '<a class="nav-link" href="{% url \'core:dashboard\' %}">My workspace</a>'
        addition = ("\n          <!-- SMARTMART_STAGE3_NAV -->\n"
                    "          {% if user.is_superuser or user.store_profile.is_approved %}\n"
                    "          <a class=\"nav-link\" href=\"{% url 'inventory:product_list' %}\">Products</a>\n"
                    "          {% if user.is_superuser or user.store_profile.role == 'WAREHOUSE' or user.store_profile.role == 'MANAGER' %}\n"
                    "          <a class=\"nav-link\" href=\"{% url 'inventory:stock_list' %}\">Inventory</a>\n"
                    "          {% endif %}{% endif %}\n")
        if anchor not in base:
            stop("Core navigation has been customized. Cannot safely add links; see backup.")
        base = base.replace(anchor, anchor + addition, 1)
    BASE_HTML.write_text(base, encoding="utf-8")

    admin = source[ADMIN_HTML]
    if "SMARTMART_STAGE3_ADMIN" not in admin:
        marker = '<div class="profile-strip">'
        fragment = ("<!-- SMARTMART_STAGE3_ADMIN -->\n"
            '<div class="dashboard-cards" style="margin-top:18px">'
            '<section class="dashboard-card"><div class="card-icon green">▦</div><h3>Product Catalogue</h3>'
            '<p>Create products, barcodes, categories, retail and wholesale prices.</p>'
            '<a class="dashboard-card-link" href="{% url \'inventory:product_list\' %}">Manage products →</a></section>'
            '<section class="dashboard-card"><div class="card-icon blue">▥</div><h3>Branch Inventory</h3>'
            '<p>Monitor stock by branch, receive deliveries and review low-stock items.</p>'
            '<a class="dashboard-card-link" href="{% url \'inventory:stock_list\' %}">View inventory →</a></section>'
            '<section class="dashboard-card"><div class="card-icon orange">≡</div><h3>Stock Audit Trail</h3>'
            '<p>See stock movement history and the employee who recorded it.</p>'
            '<a class="dashboard-card-link" href="{% url \'inventory:movements\' %}">View movements →</a></section></div>\n')
        admin = admin.replace(marker, fragment + marker, 1)
        admin = admin.replace("Stage 3: Product catalogue, barcode inventory, and stock levels.",
                              "Stage 3 live: product catalogue, barcode inventory and branch stock. Stage 4: Checkout and POS.")
    ADMIN_HTML.write_text(admin, encoding="utf-8")

    staff = source[STAFF_HTML]
    if "SMARTMART_STAGE3_STAFF" not in staff:
        marker = '<div class="profile-strip">'
        fragment = ("<!-- SMARTMART_STAGE3_STAFF -->\n"
          '{% if profile.role == "WAREHOUSE" or profile.role == "MANAGER" %}'
          '<div class="dashboard-cards" style="margin-top:18px">'
          '<section class="dashboard-card"><div class="card-icon green">▥</div><h3>My Branch Inventory</h3>'
          '<p>See stock levels, reorder alerts and receive new deliveries.</p>'
          '<a class="dashboard-card-link" href="{% url \'inventory:stock_list\' %}">Open branch stock →</a></section>'
          '<section class="dashboard-card"><div class="card-icon blue">≡</div><h3>Stock Movement History</h3>'
          '<p>Review stock receipts and adjustments at your branch.</p>'
          '<a class="dashboard-card-link" href="{% url \'inventory:movements\' %}">View movement history →</a></section>'
          '<section class="dashboard-card"><div class="card-icon orange">▦</div><h3>Product Lookup</h3>'
          '<p>Find items by name, SKU or barcode.</p>'
          '<a class="dashboard-card-link" href="{% url \'inventory:product_list\' %}">Browse products →</a></section></div>'
          '{% else %}<div class="profile-strip"><div><strong>Product Lookup</strong>'
          '<p>Find a product, barcode and current retail price.</p></div>'
          '<a class="button button-soft" href="{% url \'inventory:product_list\' %}">Browse products →</a></div>{% endif %}\n')
        staff = staff.replace(marker, fragment + marker, 1)
    STAFF_HTML.write_text(staff, encoding="utf-8")

    run("check")
    run("makemigrations", "inventory", "--noinput")
    run("migrate", "--noinput")
    run("seed_categories")
    run("test", "inventory", "core")
    print("\nSUCCESS: SmartMart Stage 3 installed and tests passed.")
    print("Now run: python manage.py runserver 8002")
    print("Admin: log in, open Product Catalogue, add the first product.")
    print("Warehouse: log in, open My Branch Inventory and record a receipt.")
    print("Backup:", prior)


if __name__ == "__main__":
    main()
