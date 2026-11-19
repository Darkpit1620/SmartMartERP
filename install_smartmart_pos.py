"""SmartMart ERP Stage 4 POS installer (run next to manage.py).

- Adds a new POS Django app without replacing current models or the database.
- Keeps stage 2/3 and bulk-catalogue data intact.
- Applies only small idempotent navigation updates to existing templates.
- Backs up the live SQLite file plus every existing file before editing.
"""
from datetime import datetime
from pathlib import Path
import re
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
SETTINGS = ROOT / 'config' / 'settings.py'
URLS = ROOT / 'config' / 'urls.py'
BASE = ROOT / 'core' / 'templates' / 'core' / 'base.html'
ADMIN = ROOT / 'core' / 'templates' / 'core' / 'admin_portal.html'
STAFF = ROOT / 'core' / 'templates' / 'core' / 'staff_portal.html'


def stop(message):
    raise SystemExit('\nSTAGE 4 STOPPED SAFELY: ' + message)


def cmd(*args):
    print('\nRunning: python manage.py ' + ' '.join(args), flush=True)
    result = subprocess.run([sys.executable, str(ROOT / 'manage.py'), *args], cwd=ROOT)
    if result.returncode != 0:
        stop('Django reported an error. Your backups remain untouched. Fix the printed error before rerunning.')


def backup_existing(files):
    location = ROOT / 'SmartMart_Stage4_Backups' / datetime.now().strftime('%Y%m%d_%H%M%S_%f')
    for path in files:
        if path.is_file():
            target = location / path.relative_to(ROOT)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)
    db = ROOT / 'db.sqlite3'
    if db.is_file():
        location.mkdir(parents=True, exist_ok=True)
        shutil.copy2(db, location / 'db.sqlite3')
    print('Backup created:', location)
    return location


def main():
    print('\nSMARTMART ERP STAGE 4 — POINT OF SALE')
    needed = [
        ROOT / 'manage.py', SETTINGS, URLS, BASE, ADMIN, STAFF,
        ROOT / 'core' / 'models.py', ROOT / 'inventory' / 'models.py',
        ROOT / 'pos' / 'models.py', ROOT / 'pos' / 'urls.py',
        ROOT / 'pos' / 'services.py', ROOT / 'pos' / 'tests.py',
    ]
    missing = [str(p.relative_to(ROOT)) for p in needed if not p.is_file()]
    if missing:
        stop('Files are missing: ' + ', '.join(missing) + '. Extract ZIP into SmartMartERP next to manage.py.')
    if 'class Branch(' not in (ROOT / 'core' / 'models.py').read_text(encoding='utf-8'):
        stop('core.Branch is missing. Install the original Stage 2 portal first.')
    if 'class BranchStock(' not in (ROOT / 'inventory' / 'models.py').read_text(encoding='utf-8'):
        stop('inventory.BranchStock is missing. Install Stage 3 Inventory first.')

    files = [SETTINGS, URLS, BASE, ADMIN, STAFF]
    source = {path: path.read_text(encoding='utf-8') for path in files}
    if 'inventory.apps.InventoryConfig' not in source[SETTINGS]:
        stop('Stage 3 Inventory is not registered in INSTALLED_APPS.')
    if 'core.apps.CoreConfig' not in source[SETTINGS]:
        stop('Stage 2 Core is not registered in INSTALLED_APPS.')
    if not re.search(r'(?m)^\s*INSTALLED_APPS\s*=\s*\[\s*\n', source[SETTINGS]):
        stop('Expected INSTALLED_APPS = [ in config/settings.py.')
    if not re.search(r'(?m)^from django\.urls import [^\n]+$', source[URLS]):
        stop('Expected from django.urls import ... in config/urls.py.')
    if not re.search(r'(?m)^\s*urlpatterns\s*=\s*\[\s*\n', source[URLS]):
        stop('Could not find the URL patterns list.')
    nav_marker = '<a class="nav-link" href="{% url \'core:dashboard\' %}">My workspace</a>'
    if nav_marker not in source[BASE] and 'SMARTMART_POS_NAV' not in source[BASE]:
        stop('The main navigation is customized. No files changed; contact us to patch its exact version.')
    if '</head>' not in source[BASE]:
        stop('Shared base template is missing </head>.')
    if '{% endblock %}' not in source[STAFF] or '{% endblock %}' not in source[ADMIN]:
        stop('Dashboard template block is customized. No files changed.')

    old = backup_existing(files)
    settings = source[SETTINGS]
    if 'pos.apps.PosConfig' not in settings:
        m = re.search(r'(?m)^\s*INSTALLED_APPS\s*=\s*\[\s*\n', settings)
        settings = settings[:m.end()] + '    "pos.apps.PosConfig",\n' + settings[m.end():]
    SETTINGS.write_text(settings, encoding='utf-8')

    urls = source[URLS]
    if 'include("pos.urls")' not in urls and "include('pos.urls')" not in urls:
        m = re.search(r'(?m)^from django\.urls import ([^\n]+)$', urls)
        values = [value.strip() for value in m.group(1).split(',')]
        if 'include' not in values:
            values.append('include')
        urls = urls[:m.start()] + 'from django.urls import ' + ', '.join(values) + urls[m.end():]
        m = re.search(r'(?m)^\s*urlpatterns\s*=\s*\[\s*\n', urls)
        urls = urls[:m.end()] + '    path("pos/", include("pos.urls")),\n' + urls[m.end():]
    URLS.write_text(urls, encoding='utf-8')

    base = source[BASE]
    if 'SMARTMART_POS_NAV' not in base:
        fragment = (
            '\n          <!-- SMARTMART_POS_NAV -->\n'
            '          {% if user.is_superuser or user.store_profile.role == "CASHIER" or user.store_profile.role == "MANAGER" %}\n'
            '          <a class="nav-link" href="{% url \'pos:index\' %}">Checkout / POS</a>\n'
            '          {% endif %}'
        )
        base = base.replace(nav_marker, nav_marker + fragment, 1)
    BASE.write_text(base, encoding='utf-8')

    admin = source[ADMIN]
    if 'SMARTMART_POS_ADMIN' not in admin:
        fragment = (
            '<!-- SMARTMART_POS_ADMIN -->\n'
            '<div class="dashboard-cards" style="margin-top:18px">'
            '<section class="dashboard-card"><div class="card-icon green">▣</div>'
            '<h3>Cashier Point of Sale</h3><p>Sell products, issue printed receipts and review payments.</p>'
            '<a class="dashboard-card-link" href="{% url \'pos:index\' %}">Open POS →</a></section>'
            '<section class="dashboard-card"><div class="card-icon blue">▤</div>'
            '<h3>Sales and Receipts</h3><p>Review branch sales and outstanding payment verifications.</p>'
            '<a class="dashboard-card-link" href="{% url \'pos:sales\' %}">View sales →</a>'
            '</section></div>\n'
        )
        if '<div class="profile-strip">' in admin:
            admin = admin.replace('<div class="profile-strip">', fragment + '<div class="profile-strip">', 1)
        else:
            admin = admin.replace('{% endblock %}', fragment + '{% endblock %}', 1)
    ADMIN.write_text(admin, encoding='utf-8')

    staff = source[STAFF]
    if 'SMARTMART_POS_STAFF' not in staff:
        # A separate, role-filtered section avoids corrupting Stage 3's nested profile strips.
        fragment = (
            '\n<!-- SMARTMART_POS_STAFF -->\n'
            '{% if profile.role == "CASHIER" or profile.role == "MANAGER" %}'
            '<div class="wrap" style="margin-top:22px;margin-bottom:32px">'
            '<div class="profile-strip"><div><strong>Point of Sale is available</strong>'
            '<p>Scan products, complete checkout, and print receipts for your branch.</p></div>'
            '<div><a class="button button-primary" href="{% url \'pos:index\' %}">Open Cashier POS →</a>'
            ' <a class="button button-soft" href="{% url \'pos:sales\' %}">Sales &amp; receipts</a></div>'
            '</div></div>{% endif %}\n'
        )
        staff = staff.replace('{% endblock %}', fragment + '{% endblock %}', 1)
    # Activate the original cashier dashboard card, replacing its Stage 2 coming-soon label.
    marker = '<span class="coming-soon">Planned module · Coming next</span>'
    if 'SMARTMART_POS_MODULE_CARD' not in staff and marker in staff:
        replacement = (
            '<!-- SMARTMART_POS_MODULE_CARD -->'
            '{% if profile.role == "CASHIER" and title == "Checkout / POS" %}'
            '<a class="dashboard-card-link" href="{% url \'pos:index\' %}">Launch Checkout →</a>'
            '{% elif profile.role == "MANAGER" and title == "Sales overview" %}'
            '<a class="dashboard-card-link" href="{% url \'pos:sales\' %}">View Branch Sales →</a>'
            '{% else %}' + marker + '{% endif %}'
        )
        staff = staff.replace(marker, replacement, 1)
    STAFF.write_text(staff, encoding='utf-8')

    cmd('check')
    cmd('makemigrations', 'pos', '--noinput')
    cmd('migrate', '--noinput')
    cmd('test', 'pos', '--noinput')
    print('\nSUCCESS: POS installed and its Django tests passed.')
    print('Start the server: python manage.py runserver 8002')
    print('Open homepage, log in as an approved cashier, then select Checkout / POS.')
    print('Optional sample sale: python manage.py setup_pos_demo')
    print('Backup folder:', old)


if __name__ == '__main__':
    main()
