"""SmartMart ERP Stage 5 installer. Run from the SmartMartERP folder.

Adds the 'trading' app; preserves Stage 2 Core, Stage 3 Inventory,
Stage 4 POS, user accounts, real prices, all stocks and completed sales.
"""
import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SETTINGS = ROOT / 'config/settings.py'
URLS = ROOT / 'config/urls.py'
BASE = ROOT / 'core/templates/core/base.html'
ADMIN = ROOT / 'core/templates/core/admin_portal.html'
STAFF = ROOT / 'core/templates/core/staff_portal.html'


def stop(message):
    raise SystemExit('\nSTAGE 5 STOPPED SAFELY: ' + message)


def manage(*args):
    print('\nRunning: python manage.py ' + ' '.join(args), flush=True)
    status = subprocess.run([sys.executable, str(ROOT / 'manage.py'), *args], cwd=ROOT)
    if status.returncode:
        stop('Django reported an error. Review the output. A backup was created before modifying files.')


def make_backup(files):
    dest = ROOT / 'SmartMart_Stage5_Backups' / datetime.now().strftime('%Y%m%d_%H%M%S_%f')
    for src in files:
        if src.is_file():
            path = dest / src.relative_to(ROOT)
            path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, path)
    db = ROOT / 'db.sqlite3'
    if db.is_file():
        dest.mkdir(parents=True, exist_ok=True)
        shutil.copy2(db, dest / 'db.sqlite3')
    print('Backup created:', dest)
    return dest


def install():
    print('\nSMARTMART ERP STAGE 5 — SUPPLIERS, PURCHASING & WHOLESALE\n')
    needed = [ROOT / 'manage.py', SETTINGS, URLS, BASE, ADMIN, STAFF,
              ROOT / 'core/models.py', ROOT / 'inventory/models.py',
              ROOT / 'inventory/services.py', ROOT / 'pos/models.py',
              ROOT / 'pos/services.py', ROOT / 'trading/models.py',
              ROOT / 'trading/tests.py', ROOT / 'trading/urls.py']
    missing = [str(path.relative_to(ROOT)) for path in needed if not path.is_file()]
    if missing:
        stop('Missing files: ' + ', '.join(missing) + '. Extract the Stage 5 ZIP alongside manage.py.')
    if 'class BranchStock(' not in (ROOT / 'inventory/models.py').read_text(encoding='utf-8'):
        stop('Stage 3 inventory models were not recognized.')
    if 'def complete_sale(' not in (ROOT / 'pos/services.py').read_text(encoding='utf-8'):
        stop('Stage 4 POS checkout service was not recognized.')

    files = [SETTINGS, URLS, BASE, ADMIN, STAFF]
    contents = {p: p.read_text(encoding='utf-8') for p in files}
    if not all(x in contents[SETTINGS] for x in ('core.apps.CoreConfig', 'inventory.apps.InventoryConfig', 'pos.apps.PosConfig')):
        stop('Install Stages 2, 3, and 4 first. No changes made.')
    if not re.search(r'(?m)^\s*INSTALLED_APPS\s*=\s*\[\s*\n', contents[SETTINGS]):
        stop('Could not locate the INSTALLED_APPS list in settings.py. No changes made.')
    if not re.search(r'(?m)^from django\.urls import ([^\n]+)$', contents[URLS]):
        stop('Could not find Django URL imports. No changes made.')
    if not re.search(r'(?m)^\s*urlpatterns\s*=\s*\[\s*\n', contents[URLS]):
        stop('Could not locate urlpatterns. No changes made.')
    if '</head>' not in contents[BASE] or '</nav>' not in contents[BASE]:
        stop('Unrecognized shared base template. No changes made.')
    if '{% endblock %}' not in contents[ADMIN] or '{% endblock %}' not in contents[STAFF]:
        stop('Unrecognized dashboards. No changes made.')
    if 'SMARTMART_TRADE_NAV' not in contents[BASE] and 'My workspace</a>' not in contents[BASE]:
        stop('Could not find existing navigation insertion point. No changes made.')

    backup = make_backup(files)

    settings = contents[SETTINGS]
    if 'trading.apps.TradingConfig' not in settings:
        m = re.search(r'(?m)^\s*INSTALLED_APPS\s*=\s*\[\s*\n', settings)
        settings = settings[:m.end()] + '    "trading.apps.TradingConfig",\n' + settings[m.end():]
    SETTINGS.write_text(settings, encoding='utf-8')

    urls = contents[URLS]
    if 'include("trading.urls")' not in urls and "include('trading.urls')" not in urls:
        m = re.search(r'(?m)^from django\.urls import ([^\n]+)$', urls)
        values = [part.strip() for part in m.group(1).split(',')]
        if 'include' not in values:
            values.append('include')
        urls = urls[:m.start()] + 'from django.urls import ' + ', '.join(values) + urls[m.end():]
        m = re.search(r'(?m)^\s*urlpatterns\s*=\s*\[\s*\n', urls)
        urls = urls[:m.end()] + '    path("trade/", include("trading.urls")),\n' + urls[m.end():]
    URLS.write_text(urls, encoding='utf-8')

    base = contents[BASE]
    if 'SMARTMART_TRADE_CSS' not in base:
        base = base.replace('</head>', "  <!-- SMARTMART_TRADE_CSS -->\n  <link rel=\"stylesheet\" href=\"{% static 'trading/css/trading.css' %}\">\n</head>", 1)
    if 'SMARTMART_TRADE_NAV' not in base:
        marker = '<a class="nav-link" href="{% url \'core:dashboard\' %}">My workspace</a>'
        fragment = ('\n          <!-- SMARTMART_TRADE_NAV -->\n'
                    '          {% if user.is_superuser or user.store_profile.role == "MANAGER" or user.store_profile.role == "WAREHOUSE" %}\n'
                    '          <a class="nav-link" href="{% url \'trading:home\' %}">Wholesale &amp; Purchasing</a>\n'
                    '          {% endif %}')
        base = base.replace(marker, marker + fragment, 1)
    BASE.write_text(base, encoding='utf-8')

    admin = contents[ADMIN]
    if 'SMARTMART_TRADE_ADMIN' not in admin:
        cards = ("\n<!-- SMARTMART_TRADE_ADMIN -->\n"
                 '<div class="dashboard-cards" style="margin-top:18px">'
                 '<section class="dashboard-card"><div class="card-icon green">▣</div><h3>Suppliers &amp; Purchasing</h3>'
                 '<p>Order products, receive deliveries, and audit supplier receipts.</p>'
                 '<a class="dashboard-card-link" href="{% url \'trading:home\' %}">Open purchasing →</a></section>'
                 '<section class="dashboard-card"><div class="card-icon orange">▦</div><h3>Wholesale Orders</h3>'
                 '<p>Manage bulk customer orders and fulfill them with official POS receipts.</p>'
                 '<a class="dashboard-card-link" href="{% url \'trading:home\' %}">Open wholesale →</a></section>'
                 '</div>\n')
        admin = admin.replace('{% endblock %}', cards + '{% endblock %}', 1)
    ADMIN.write_text(admin, encoding='utf-8')

    staff = contents[STAFF]
    if 'SMARTMART_TRADE_STAFF' not in staff:
        block = ("\n<!-- SMARTMART_TRADE_STAFF -->\n"
                 '{% if profile.role == "MANAGER" or profile.role == "WAREHOUSE" %}'
                 '<div class="wrap" style="margin-top:18px;margin-bottom:30px">'
                 '<div class="profile-strip"><div><strong>Suppliers &amp; Purchasing</strong>'
                 '<p>Receive supplier deliveries and manage bulk orders for your assigned branch.</p></div>'
                 '<a class="button button-primary" href="{% url \'trading:home\' %}">Open wholesale &amp; purchasing →</a>'
                 '</div></div>{% endif %}\n')
        staff = staff.replace('{% endblock %}', block + '{% endblock %}', 1)
    STAFF.write_text(staff, encoding='utf-8')

    manage('check')
    manage('makemigrations', 'trading', '--noinput')
    manage('migrate', '--noinput')
    manage('test', 'trading', '--noinput')
    print('\nSTAGE 5 INSTALLED. Open SmartMart ERP and choose Wholesale & Purchasing.')
    print('Command: python manage.py runserver 8002')
    print('Backup folder:', backup)


if __name__ == '__main__':
    install()
