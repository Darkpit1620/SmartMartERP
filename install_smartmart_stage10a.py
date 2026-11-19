"""Install SmartMart ERP Stage 10A bulk pricing on an existing Stage 9 project.

Run after extracting SmartMartERP_Stage10A_Bulk_Pricing.zip into the
SmartMartERP folder: python install_smartmart_stage10a.py

Safe and repeatable: no migrations, no inventory edits, no imports of sample prices.
"""

from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
SETTINGS = ROOT / "config" / "settings.py"
URLS = ROOT / "config" / "urls.py"
BASE = ROOT / "core" / "templates" / "core" / "base.html"
ADMIN = ROOT / "core" / "templates" / "core" / "admin_portal.html"
APP = ROOT / "pricing_portal"


def fail(message):
    raise SystemExit("\nINSTALLATION STOPPED SAFELY: " + message)


def run(*args):
    print("RUNNING: python manage.py " + " ".join(args), flush=True)
    ret = subprocess.run([sys.executable, str(ROOT / "manage.py"), *args], cwd=ROOT, check=False)
    if ret.returncode:
        fail("Django reported an error. Your verified pre-install backup remains available. Do not reset your database.")


def planned_edits():
    required = [ROOT / "manage.py", SETTINGS, URLS, BASE, ADMIN,
                ROOT / "inventory" / "models.py", ROOT / "smartmart_bulk" / "apps.py",
                ROOT / "smartmart_backup.py", APP / "urls.py", APP / "views.py",
                APP / "tests.py"]
    missing = [str(path.relative_to(ROOT)) for path in required if not path.exists()]
    if missing:
        fail("Missing file(s): " + ", ".join(missing) + ". Verify you are using the existing SmartMartERP project with Stage 9 installed.")
    current = {p: p.read_text(encoding="utf-8") for p in (SETTINGS, URLS, BASE, ADMIN)}
    if "inventory.apps.InventoryConfig" not in current[SETTINGS] or "smartmart_bulk.apps.SmartmartBulkConfig" not in current[SETTINGS]:
        fail("Stage 3 Inventory and Stage 3B Bulk Catalogue must be installed first.")
    settings = current[SETTINGS]
    if "pricing_portal.apps.PricingPortalConfig" not in settings:
        match = re.search(r"(?m)^\s*INSTALLED_APPS\s*=\s*\[\s*\n", settings)
        if not match:
            fail("Could not locate INSTALLED_APPS. Nothing changed.")
        settings = settings[:match.end()] + '    "pricing_portal.apps.PricingPortalConfig",\n' + settings[match.end():]
    urls = current[URLS]
    if not re.search(r"\binclude\s*\(\s*['\"]pricing_portal\.urls['\"]\s*\)", urls):
        match = re.search(r"(?m)^from django\.urls import ([^\n]+)$", urls)
        paths = re.search(r"(?m)^\s*urlpatterns\s*=\s*\[\s*\n", urls)
        if not match or not paths:
            fail("Could not safely locate Django URL configuration. Nothing changed.")
        imports = [name.strip() for name in match.group(1).split(",")]
        for name in ("path", "include"):
            if name not in imports:
                imports.append(name)
        urls = urls[:match.start()] + "from django.urls import " + ", ".join(imports) + urls[match.end():]
        # Re-locate after import patch to avoid outdated character offsets.
        paths = re.search(r"(?m)^\s*urlpatterns\s*=\s*\[\s*\n", urls)
        urls = urls[:paths.end()] + '    path("pricing/", include("pricing_portal.urls")),\n' + urls[paths.end():]
    base = current[BASE]
    nav_anchor = '<a class="nav-link" href="{% url \'core:dashboard\' %}">My workspace</a>'
    if "SMARTMART_PRICING_NAV" not in base:
        if nav_anchor not in base:
            fail("Unexpected custom navigation. Nothing changed. Add the Pricing link manually after backing up.")
        nav = ('\n          <!-- SMARTMART_PRICING_NAV -->\n'
               '          {% if user.is_superuser %}\n'
               '          <a class="nav-link" href="{% url \'pricing_portal:home\' %}">Bulk pricing</a>\n'
               '          {% endif %}')
        base = base.replace(nav_anchor, nav_anchor + nav, 1)
    if "SMARTMART_PRICING_CSS" not in base:
        if "</head>" not in base:
            fail("Unable to add pricing stylesheet safely. Nothing changed.")
        css = ('  <!-- SMARTMART_PRICING_CSS -->\n'
               '  <link rel="stylesheet" href="{% static \'pricing_portal/css/pricing.css\' %}">\n')
        base = base.replace("</head>", css + "</head>", 1)
    admin = current[ADMIN]
    if "SMARTMART_PRICING_ADMIN" not in admin:
        idx = admin.rfind("{% endblock %}")
        if idx < 0:
            fail("Could not safely locate the admin template block. Nothing changed.")
        card = ("\n<!-- SMARTMART_PRICING_ADMIN -->\n"
                '<section class="wrap" style="padding:16px 0 30px">'
                '<div class="profile-strip"><div><strong>Bulk Product Pricing</strong>'
                '<p>Export the full catalogue and import verified retail, wholesale, and cost prices.</p>'
                '</div><a class="button button-primary" href="{% url \'pricing_portal:home\' %}">Manage product prices →</a>'
                '</div></section>\n')
        admin = admin[:idx] + card + admin[idx:]
    return current, {SETTINGS: settings, URLS: urls, BASE: base, ADMIN: admin}


def install():
    print("SMARTMART ERP · STAGE 10A · BULK PRODUCT PRICING", flush=True)
    original, changed = planned_edits()
    # The Stage 9 tool verifies the SQLite backup and stores it outside this project.
    from smartmart_backup import create_backup
    try:
        saved = create_backup()
    except Exception as exc:
        fail("Database backup failed; no configuration files modified. " + str(exc))
    backup_dir = saved / "preinstall_files"
    for file, body in original.items():
        target = backup_dir / file.relative_to(ROOT)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(body, encoding="utf-8")
    print("VERIFIED PRIVATE BACKUP:", saved, flush=True)
    for file, body in changed.items():
        if body != original[file]:
            file.write_text(body, encoding="utf-8")
    run("check")
    run("test", "pricing_portal", "--noinput")
    print("\nSTAGE 10A INSTALLED. No product prices or stock were changed.")
    print("Start: python manage.py runserver 8002")
    print("Admin Workspace → Bulk Product Pricing → Download full price CSV.")
    print("Fill verified prices, then preview and import the CSV.")
    print("Backup:", saved)


if __name__ == "__main__":
    install()
