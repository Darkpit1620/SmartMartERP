"""Install SmartMart ERP Stage 6 safely beside manage.py.

Requires Stage 2 Core, Stage 3 Inventory, Stage 4 POS, and Stage 5 Trading.
Use `python install_smartmart_stage6.py` once after extracting ZIP.
This does NOT seed fake inventory, delete data or overwrite old models wholesale.
"""
from datetime import datetime
import re
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SETTINGS = ROOT / 'config/settings.py'
URLS = ROOT / 'config/urls.py'
BASE = ROOT / 'core/templates/core/base.html'
ADMIN = ROOT / 'core/templates/core/admin_portal.html'
STAFF = ROOT / 'core/templates/core/staff_portal.html'
STOCK_MODELS = ROOT / 'inventory/models.py'
STOCK_SERVICES = ROOT / 'inventory/services.py'
STOCK_FORMS = ROOT / 'inventory/forms.py'


def stop(message):
    raise SystemExit('\nSTAGE 6 STOPPED SAFELY: ' + message)


def manage(*args):
    print('\nRunning: python manage.py ' + ' '.join(args), flush=True)
    result = subprocess.run([sys.executable, str(ROOT / 'manage.py'), *args], cwd=ROOT)
    if result.returncode:
        stop('Django reported an error. Review the output. Your backup exists. Do not reset the database.')


def make_backup(files):
    dest = ROOT / 'SmartMart_Stage6_Backups' / datetime.now().strftime('%Y%m%d_%H%M%S_%f')
    for src in files:
        target = dest / src.relative_to(ROOT)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, target)
    db = ROOT / 'db.sqlite3'
    if db.is_file():
        dest.mkdir(parents=True, exist_ok=True)
        # Native SQLite backup is safer than copying an open database file.
        source = sqlite3.connect(str(db))
        backup = sqlite3.connect(str(dest / 'db.sqlite3'))
        try:
            source.backup(backup)
        finally:
            backup.close()
            source.close()
    print('Safety backup created:', dest)
    return dest


def patch_stock_models(value):
    marker = 'TRANSFER_OUT = "TRANSFER_OUT", "Dispatched branch transfer"'
    if marker in value or 'TRANSFER_OUT = ' in value:
        return value
    pattern = r'(?m)^(\s*CORRECTION_OUT\s*=\s*[^\n]+\n)'
    matched = re.search(pattern, value)
    if not matched:
        stop('Cannot locate the original inventory stock movement kinds. No changes made.')
    indentation = re.match(r'^\s*', matched.group(1)).group(0)
    patch = (f'{indentation}TRANSFER_OUT = "TRANSFER_OUT", "Dispatched branch transfer"\n'
             f'{indentation}TRANSFER_IN = "TRANSFER_IN", "Received branch transfer"\n')
    return value[:matched.end()] + patch + value[matched.end():]


def patch_stock_services(value):
    if 'StockMovement.Kind.TRANSFER_OUT' in value:
        return value
    old = 'if kind == StockMovement.Kind.CORRECTION_OUT:'
    if old not in value:
        stop('Cannot safely extend stock service subtraction logic. No changes made.')
    return value.replace(old, 'if kind in (StockMovement.Kind.CORRECTION_OUT, StockMovement.Kind.TRANSFER_OUT):', 1)


def patch_stock_forms(value):
    if "if value in ('RECEIPT', 'CORRECTION_IN', 'CORRECTION_OUT')" in value:
        return value
    old = 'choices=StockMovement.Kind.choices'
    if old not in value:
        stop('Cannot safely lock the manual stock form to its original movement types. No changes made.')
    replace = "choices=[(value, label) for value, label in StockMovement.Kind.choices if value in ('RECEIPT', 'CORRECTION_IN', 'CORRECTION_OUT')]"
    return value.replace(old, replace, 1)


def install():
    print('\nSMARTMART ERP STAGE 6 — MULTI-BRANCH TRANSFERS AND WAREHOUSES\n')
    required = [ROOT / 'manage.py', SETTINGS, URLS, BASE, ADMIN, STAFF,
                STOCK_MODELS, STOCK_SERVICES, STOCK_FORMS,
                ROOT / 'core/models.py', ROOT / 'pos/models.py', ROOT / 'trading/models.py',
                ROOT / 'transfers/models.py', ROOT / 'transfers/urls.py', ROOT / 'transfers/tests.py']
    missing = [str(p.relative_to(ROOT)) for p in required if not p.is_file()]
    if missing:
        stop('Missing: ' + ', '.join(missing) + '. Extract ZIP alongside manage.py after Stages 2–5.')
    sources = {p: p.read_text(encoding='utf-8') for p in (SETTINGS, URLS, BASE, ADMIN, STAFF, STOCK_MODELS, STOCK_SERVICES, STOCK_FORMS)}
    settings = sources[SETTINGS]
    if not all(x in settings for x in ('core.apps.CoreConfig', 'inventory.apps.InventoryConfig',
                                       'pos.apps.PosConfig', 'trading.apps.TradingConfig')):
        stop('Stages 2, 3, 4 and 5 must be installed first. No changes made.')
    m_settings = re.search(r'(?m)^\s*INSTALLED_APPS\s*=\s*\[\s*\n', settings)
    m_urls = re.search(r'(?m)^\s*urlpatterns\s*=\s*\[\s*\n', sources[URLS])
    m_import = re.search(r'(?m)^from django\.urls import ([^\n]+)$', sources[URLS])
    if not (m_settings and m_urls and m_import):
        stop('Cannot locate standard Django settings or URL patterns. No changes made.')
    if '</head>' not in sources[BASE] or '</nav>' not in sources[BASE]:
        stop('Could not recognise the shared layout. No changes made.')
    if 'SMARTMART_TRANSFER_NAV' not in sources[BASE] and 'My workspace</a>' not in sources[BASE]:
        stop('Could not find the navigation insertion point. No changes made.')
    if '{% endblock %}' not in sources[ADMIN] or '{% endblock %}' not in sources[STAFF]:
        stop('Could not find the dashboard insertion point. No changes made.')
    if 'class StockMovement(models.Model):' not in sources[STOCK_MODELS] or 'def record_stock_movement(' not in sources[STOCK_SERVICES]:
        stop('Stage 3 stock models or services have changed unexpectedly. No changes made.')
    # Calculate and verify every patch BEFORE editing files.
    updates = {}
    updates[STOCK_MODELS] = patch_stock_models(sources[STOCK_MODELS])
    updates[STOCK_SERVICES] = patch_stock_services(sources[STOCK_SERVICES])
    updates[STOCK_FORMS] = patch_stock_forms(sources[STOCK_FORMS])

    if 'transfers.apps.TransfersConfig' not in settings:
        m = re.search(r'(?m)^\s*INSTALLED_APPS\s*=\s*\[\s*\n', settings)
        settings = settings[:m.end()] + '    "transfers.apps.TransfersConfig",\n' + settings[m.end():]
    updates[SETTINGS] = settings

    urls = sources[URLS]
    if 'include("transfers.urls")' not in urls and "include('transfers.urls')" not in urls:
        import_match = re.search(r'(?m)^from django\.urls import ([^\n]+)$', urls)
        names = [name.strip() for name in import_match.group(1).split(',')]
        if 'include' not in names:
            names.append('include')
        urls = urls[:import_match.start()] + 'from django.urls import ' + ', '.join(names) + urls[import_match.end():]
        pattern_match = re.search(r'(?m)^\s*urlpatterns\s*=\s*\[\s*\n', urls)
        urls = urls[:pattern_match.end()] + '    path("transfers/", include("transfers.urls")),\n' + urls[pattern_match.end():]
    updates[URLS] = urls

    base = sources[BASE]
    if 'SMARTMART_TRANSFER_CSS' not in base:
        base = base.replace('</head>', "  <!-- SMARTMART_TRANSFER_CSS -->\n  <link rel=\"stylesheet\" href=\"{% static 'transfers/css/transfers.css' %}\">\n</head>", 1)
    if 'SMARTMART_TRANSFER_NAV' not in base:
        marker = '<a class="nav-link" href="{% url \'core:dashboard\' %}">My workspace</a>'
        fragment = ("\n          <!-- SMARTMART_TRANSFER_NAV -->\n"
                    "          {% if user.is_superuser or user.store_profile.role == 'MANAGER' or user.store_profile.role == 'WAREHOUSE' %}\n"
                    "          <a class=\"nav-link\" href=\"{% url 'transfers:list' %}\">Branch transfers</a>\n"
                    "          {% endif %}")
        base = base.replace(marker, marker + fragment, 1)
    updates[BASE] = base

    admin = sources[ADMIN]
    if 'SMARTMART_TRANSFER_ADMIN' not in admin:
        fragment = ("\n<!-- SMARTMART_TRANSFER_ADMIN -->\n<div class=\"dashboard-cards\" style=\"margin-top:18px\">"
                    "<section class=\"dashboard-card\"><div class=\"card-icon green\">⇄</div>"
                    "<h3>Branch Stock Transfers</h3><p>Dispatch, receive, and audit stock movements across supermarket branches.</p>"
                    "<a class=\"dashboard-card-link\" href=\"{% url 'transfers:list' %}\">Manage transfers →</a>"
                    "</section></div>\n")
        admin = admin.replace('{% endblock %}', fragment + '{% endblock %}', 1)
    updates[ADMIN] = admin

    staff = sources[STAFF]
    if 'SMARTMART_TRANSFER_STAFF' not in staff:
        fragment = ("\n<!-- SMARTMART_TRANSFER_STAFF -->\n"
                    "{% if profile.role == 'MANAGER' or profile.role == 'WAREHOUSE' %}"
                    "<div class=\"wrap\" style=\"margin-top:18px;margin-bottom:28px\">"
                    "<div class=\"profile-strip\"><div><strong>Warehouse &amp; Branch Transfers</strong>"
                    "<p>View shipments, dispatch stock and confirm deliveries for your branch.</p></div>"
                    "<a class=\"button button-primary\" href=\"{% url 'transfers:list' %}\">Manage branch transfers →</a>"
                    "</div></div>{% endif %}\n")
        staff = staff.replace('{% endblock %}', fragment + '{% endblock %}', 1)
    updates[STAFF] = staff

    backup_dir = make_backup(list(updates))
    for path, value in updates.items():
        if value != sources[path]:
            path.write_text(value, encoding='utf-8')
    manage('check')
    manage('makemigrations', 'inventory', 'transfers', '--noinput')
    manage('migrate', '--noinput')
    manage('test', 'transfers', '--noinput')
    print('\nSUCCESS: STAGE 6 INSTALLED')
    print('Start the server: python manage.py runserver 8002')
    print('Sign in and click Branch transfers on your dashboard.')
    print('Backup:', backup_dir)


if __name__ == '__main__':
    install()
