"""Safe SmartMart ERP Stage 8 installer.

Run inside an existing SmartMartERP project:
    python install_smartmart_stage8.py

Creates backups, patches additive routes and links, runs migrations and tests.
Never alters the existing POS, branch inventory or wholesale database records.
"""
from datetime import datetime
from pathlib import Path
import re
import shutil
import sqlite3
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
SETTINGS = ROOT / 'config/settings.py'
URLS = ROOT / 'config/urls.py'
BASE = ROOT / 'core/templates/core/base.html'
ADMIN = ROOT / 'core/templates/core/admin_portal.html'
STAFF = ROOT / 'core/templates/core/staff_portal.html'


def stop(reason):
    raise SystemExit('\nSMARTMART STAGE 8 STOPPED SAFELY: ' + reason)


def manage(*arguments):
    print('\nRUNNING: python manage.py ' + ' '.join(arguments), flush=True)
    result = subprocess.run([sys.executable, str(ROOT / 'manage.py'), *arguments], cwd=ROOT, check=False)
    if result.returncode != 0:
        stop('The Django command above failed. Read the error and keep the safety backup. Do not reset the database.')


def backup(files):
    folder = ROOT / 'SmartMart_Stage8_Backups' / datetime.now().strftime('%Y%m%d_%H%M%S_%f')
    for f in files:
        output = folder / f.relative_to(ROOT)
        output.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(f, output)
    db = ROOT / 'db.sqlite3'
    if db.exists():
        folder.mkdir(parents=True, exist_ok=True)
        original = sqlite3.connect(str(db))
        copy = sqlite3.connect(str(folder / 'db.sqlite3'))
        try:
            original.backup(copy)
        except sqlite3.Error as error:
            stop('Database backup failed. No files changed: ' + str(error))
        finally:
            copy.close()
            original.close()
    else:
        stop('Could not find db.sqlite3. Check your project folder before proceeding.')
    print('SAFETY BACKUP:', folder, flush=True)
    return folder


def install():
    print('SMARTMART ERP · STAGE 8 FINANCE AND REPORTING', flush=True)
    expected = [ROOT / 'manage.py', SETTINGS, URLS, BASE, ADMIN, STAFF,
                ROOT / 'core/models.py', ROOT / 'inventory/models.py',
                ROOT / 'pos/models.py', ROOT / 'trading/models.py',
                ROOT / 'transfers/models.py', ROOT / 'workforce/models.py',
                ROOT / 'finance_ops/models.py', ROOT / 'finance_ops/tests.py']
    missing = [str(file.relative_to(ROOT)) for file in expected if not file.is_file()]
    if missing:
        stop('Missing project files: ' + ', '.join(missing) + '. Extract the ZIP in SmartMartERP and install Stages 2–7 first.')

    current = {f: f.read_text(encoding='utf-8') for f in (SETTINGS, URLS, BASE, ADMIN, STAFF)}
    settings = current[SETTINGS]
    needed_apps = ('core.apps.CoreConfig', 'inventory.apps.InventoryConfig', 'pos.apps.PosConfig',
                   'trading.apps.TradingConfig', 'transfers.apps.TransfersConfig', 'workforce.apps.WorkforceConfig')
    if any(app not in settings for app in needed_apps):
        stop('Stages 2–7 are not all registered in config/settings.py. Install the earlier stages first.')
    match = re.search(r'(?m)^\s*INSTALLED_APPS\s*=\s*\[\s*\n', settings)
    if not match:
        stop('Cannot identify INSTALLED_APPS in config/settings.py. No changes made.')
    url_text = current[URLS]
    if not re.search(r'(?m)^from django\.urls import ([^\n]+)$', url_text) or not re.search(r'(?m)^\s*urlpatterns\s*=\s*\[\s*\n', url_text):
        stop('Cannot safely identify the routes in config/urls.py. No changes made.')
    nav_anchor = '<a class="nav-link" href="{% url \'core:dashboard\' %}">My workspace</a>'
    if '</head>' not in current[BASE] or ('SMARTMART_FINANCE_NAV' not in current[BASE] and nav_anchor not in current[BASE]):
        stop('The homepage template structure differs from the expected SmartMart version. No changes made.')
    if '{% endblock %}' not in current[ADMIN] or '{% endblock %}' not in current[STAFF]:
        stop('Dashboard templates are not compatible. No changes made.')

    changes = {}
    if 'finance_ops.apps.FinanceOpsConfig' not in settings:
        settings = settings[:match.end()] + '    "finance_ops.apps.FinanceOpsConfig",\n' + settings[match.end():]
    changes[SETTINGS] = settings

    if 'include("finance_ops.urls")' not in url_text and "include('finance_ops.urls')" not in url_text:
        imports = re.search(r'(?m)^from django\.urls import ([^\n]+)$', url_text)
        parts = [part.strip() for part in imports.group(1).split(',')]
        if 'include' not in parts:
            parts.append('include')
        url_text = url_text[:imports.start()] + 'from django.urls import ' + ', '.join(parts) + url_text[imports.end():]
        urlpatterns = re.search(r'(?m)^\s*urlpatterns\s*=\s*\[\s*\n', url_text)
        url_text = (url_text[:urlpatterns.end()] + '    path("finance/", include("finance_ops.urls")),\n'
                    + url_text[urlpatterns.end():])
    changes[URLS] = url_text

    base = current[BASE]
    if 'SMARTMART_FINANCE_NAV' not in base:
        nav = ('\n          <!-- SMARTMART_FINANCE_NAV -->\n'
               '          {% if user.is_superuser or user.store_profile.is_approved and user.store_profile.role == "MANAGER" %}\n'
               '          <a class="nav-link" href="{% url \'finance_ops:overview\' %}">Finance &amp; Reports</a>\n'
               '          {% endif %}')
        base = base.replace(nav_anchor, nav_anchor + nav, 1)
    changes[BASE] = base

    admin = current[ADMIN]
    if 'SMARTMART_FINANCE_ADMIN' not in admin:
        card = ('\n<!-- SMARTMART_FINANCE_ADMIN -->\n'
                '<section class="wrap" style="padding-top:20px;padding-bottom:15px">'
                '<div class="profile-strip"><div><strong>Finance &amp; Business Reports</strong>'
                '<p>Branch sales, verified payments, operating expenses and downloadable reports.</p></div>'
                '<a class="button button-primary" href="{% url \'finance_ops:overview\' %}">View financial reports →</a>'
                '</div></section>\n')
        last = admin.rfind('{% endblock %}')
        admin = admin[:last] + card + admin[last:]
    changes[ADMIN] = admin

    staff = current[STAFF]
    if 'SMARTMART_FINANCE_MANAGER' not in staff:
        card = ('\n<!-- SMARTMART_FINANCE_MANAGER -->\n'
                '{% if profile.role == "MANAGER" %}'
                '<section class="wrap" style="padding-top:15px;padding-bottom:30px">'
                '<div class="profile-strip"><div><strong>Branch Finance &amp; Reports</strong>'
                '<p>Review your branch sales, submit expenses and monitor payment verification.</p></div>'
                '<a class="button button-primary" href="{% url \'finance_ops:overview\' %}">Open branch finance →</a>'
                '</div></section>{% endif %}\n')
        last = staff.rfind('{% endblock %}')
        staff = staff[:last] + card + staff[last:]
    changes[STAFF] = staff

    folder = backup(list(changes))
    for file, content in changes.items():
        if content != current[file]:
            file.write_text(content, encoding='utf-8')

    manage('check')
    manage('makemigrations', 'finance_ops', '--noinput')
    manage('migrate', '--noinput')
    manage('test', 'finance_ops', '--noinput')
    print('\nSUCCESS: Stage 8 Finance and Reports installed.')
    print('Start your existing website: python manage.py runserver 8002')
    print('Sign in to the SmartMart dashboard and choose Finance & Reports.')
    print('Original files and SQLite database backed up at:', folder)


if __name__ == '__main__':
    install()
