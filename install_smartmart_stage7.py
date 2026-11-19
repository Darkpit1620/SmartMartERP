"""Install SmartMart ERP Stage 7 Workforce without replacing existing stock, sales, or users.
Run from your SmartMartERP directory: python install_smartmart_stage7.py
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


def fail(message):
    raise SystemExit('\nSTAGE 7 STOPPED SAFELY: ' + message)


def manage(*args):
    print('\nRUNNING: python manage.py ' + ' '.join(args), flush=True)
    result = subprocess.run([sys.executable, str(ROOT / 'manage.py'), *args], cwd=ROOT, check=False)
    if result.returncode:
        fail('A Django command failed. Read the error above. Your backup is preserved; do not reset the database.')


def make_backup(paths):
    backup = ROOT / 'SmartMart_Stage7_Backups' / datetime.now().strftime('%Y%m%d_%H%M%S_%f')
    for path in paths:
        out = backup / path.relative_to(ROOT)
        out.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, out)
    db = ROOT / 'db.sqlite3'
    if db.exists():
        backup.mkdir(parents=True, exist_ok=True)
        source = sqlite3.connect(str(db))
        target = sqlite3.connect(str(backup / 'db.sqlite3'))
        try:
            source.backup(target)
        except sqlite3.Error as exc:
            fail('The database backup failed: ' + str(exc) + '. Nothing was patched.')
        finally:
            target.close()
            source.close()
    print('BACKUP:', backup)
    return backup


def patch_files():
    print('SMARTMART ERP: STAGE 7 — HR, ATTENDANCE, AND LEAVE')
    required = [ROOT / 'manage.py', SETTINGS, URLS, BASE, ADMIN, STAFF,
                ROOT / 'core/models.py', ROOT / 'workforce/models.py',
                ROOT / 'workforce/tests.py', ROOT / 'transfers/models.py',
                ROOT / 'trading/models.py', ROOT / 'pos/models.py',
                ROOT / 'inventory/models.py']
    missing = [str(p.relative_to(ROOT)) for p in required if not p.is_file()]
    if missing:
        fail('Missing: ' + ', '.join(missing) + '. Install Stages 2–6 and extract this ZIP alongside manage.py.')
    old = {f: f.read_text(encoding='utf-8') for f in (SETTINGS, URLS, BASE, ADMIN, STAFF)}
    s = old[SETTINGS]
    if not all(x in s for x in ('core.apps.CoreConfig', 'inventory.apps.InventoryConfig',
                                'pos.apps.PosConfig', 'trading.apps.TradingConfig',
                                'transfers.apps.TransfersConfig')):
        fail('Install Stages 2–6 first; required Django apps are not registered.')
    if not re.search(r'(?m)^\s*INSTALLED_APPS\s*=\s*\[\s*\n', s):
        fail('Cannot locate INSTALLED_APPS in config/settings.py.')
    u = old[URLS]
    if not re.search(r'(?m)^from django\.urls import ([^\n]+)$', u) or not re.search(r'(?m)^\s*urlpatterns\s*=\s*\[\s*\n', u):
        fail('Cannot safely locate Django routes in config/urls.py.')
    base = old[BASE]
    marker = '<a class="nav-link" href="{% url \'core:dashboard\' %}">My workspace</a>'
    if '</head>' not in base or ('SMARTMART_HR_NAV' not in base and marker not in base):
        fail('The base template differs from the supported SmartMart layout. No changes made.')
    if any('{% endblock %}' not in old[p] for p in (ADMIN, STAFF)):
        fail('A dashboard template differs from the supported SmartMart layout. No changes made.')

    changes = {}
    if 'workforce.apps.WorkforceConfig' not in s:
        m = re.search(r'(?m)^\s*INSTALLED_APPS\s*=\s*\[\s*\n', s)
        s = s[:m.end()] + '    "workforce.apps.WorkforceConfig",\n' + s[m.end():]
    changes[SETTINGS] = s

    if 'include("workforce.urls")' not in u and "include('workforce.urls')" not in u:
        m = re.search(r'(?m)^from django\.urls import ([^\n]+)$', u)
        names = [n.strip() for n in m.group(1).split(',')]
        if 'include' not in names:
            names.append('include')
        u = u[:m.start()] + 'from django.urls import ' + ', '.join(names) + u[m.end():]
        m = re.search(r'(?m)^\s*urlpatterns\s*=\s*\[\s*\n', u)
        u = u[:m.end()] + '    path("workforce/", include("workforce.urls")),\n' + u[m.end():]
    changes[URLS] = u

    if 'SMARTMART_HR_CSS' not in base:
        base = base.replace('</head>', "  <!-- SMARTMART_HR_CSS -->\n  <link rel=\"stylesheet\" href=\"{% static 'workforce/css/workforce.css' %}\">\n</head>", 1)
    if 'SMARTMART_HR_NAV' not in base:
        link = ("\n          <!-- SMARTMART_HR_NAV -->\n"
                "          {% if user.is_superuser or user.store_profile.is_approved %}\n"
                "          <a class=\"nav-link\" href=\"{% url 'workforce:home' %}\">HR &amp; Attendance</a>\n"
                "          {% endif %}")
        base = base.replace(marker, marker + link, 1)
    changes[BASE] = base

    a = old[ADMIN]
    if 'SMARTMART_HR_ADMIN' not in a:
        fragment = ("\n<!-- SMARTMART_HR_ADMIN -->\n<div class=\"wrap\" style=\"padding-top:24px;padding-bottom:14px\">"
                    "<div class=\"profile-strip\"><div><strong>Employee Management &amp; HR</strong>"
                    "<p>Staff directory, branch attendance, leave approvals and employment records.</p></div>"
                    "<a class=\"button button-primary\" href=\"{% url 'workforce:team' %}\">Open HR Workspace →</a>"
                    "</div></div>\n")
        i = a.rfind('{% endblock %}')
        a = a[:i] + fragment + a[i:]
    changes[ADMIN] = a

    t = old[STAFF]
    if 'SMARTMART_HR_STAFF' not in t:
        fragment = ("\n<!-- SMARTMART_HR_STAFF -->\n<div class=\"wrap\" style=\"padding-top:18px;padding-bottom:30px\">"
                    "<div class=\"profile-strip\"><div><strong>My HR &amp; Attendance</strong>"
                    "<p>Check in, view your shifts and request leave. Branch managers can review staff leave.</p></div>"
                    "<a class=\"button button-primary\" href=\"{% url 'workforce:home' %}\">Open My HR →</a>"
                    "</div></div>\n")
        i = t.rfind('{% endblock %}')
        t = t[:i] + fragment + t[i:]
    changes[STAFF] = t

    backup = make_backup(list(changes))
    for path, updated in changes.items():
        if updated != old[path]:
            path.write_text(updated, encoding='utf-8')
    manage('check')
    manage('makemigrations', 'workforce', '--noinput')
    manage('migrate', '--noinput')
    manage('test', 'workforce', '--noinput')
    print('\nSUCCESS: Stage 7 HR and Attendance installed.')
    print('Run: python manage.py runserver 8002')
    print('Open the usual SmartMart homepage and click HR & Attendance.')
    print('To edit employee details, open Django Admin > SmartMart HR and Attendance.')
    print('Safety backup:', backup)


if __name__ == '__main__':
    patch_files()
