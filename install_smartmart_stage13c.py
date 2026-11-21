"""Stage 13C: add read-only branch reorder alerts to existing SmartMart ERP.

Non-destructive, idempotent. Uses the project's private verified backup tool.
Requires a successful Stage 13B shift installation and tests. No migrations.
"""
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
SETTINGS = ROOT / 'config' / 'settings.py'
URLS = ROOT / 'config' / 'urls.py'
BASE = ROOT / 'core' / 'templates' / 'core' / 'base.html'
ADMIN = ROOT / 'core' / 'templates' / 'core' / 'admin_portal.html'
STAFF = ROOT / 'core' / 'templates' / 'core' / 'staff_portal.html'
STOCK = ROOT / 'inventory' / 'templates' / 'inventory' / 'stock.html'
APP = ROOT / 'stock_alerts'


def stop(message):
    raise SystemExit('STAGE 13C STOPPED SAFELY: ' + str(message))


def manage(*arguments):
    print('RUNNING: python manage.py ' + ' '.join(arguments), flush=True)
    completed = subprocess.run([sys.executable, str(ROOT / 'manage.py'), *arguments], cwd=ROOT, check=False)
    if completed.returncode:
        raise RuntimeError('Django command exited with status ' + str(completed.returncode))


def prepare():
    required = [ROOT / 'manage.py', ROOT / 'smartmart_backup.py', SETTINGS, URLS, BASE, ADMIN, STAFF, STOCK,
                ROOT / 'inventory' / 'models.py', ROOT / 'inventory' / 'permissions.py',
                ROOT / 'shift_ops' / 'apps.py', ROOT / 'shift_ops' / 'tests.py',
                APP / 'apps.py', APP / 'services.py', APP / 'views.py', APP / 'urls.py', APP / 'tests.py',
                APP / 'templates' / 'stock_alerts' / 'home.html',
                APP / 'static' / 'stock_alerts' / 'css' / 'alerts.css']
    missing = [str(file.relative_to(ROOT)) for file in required if not file.is_file()]
    if missing:
        stop('Missing required files: ' + ', '.join(missing) + '. Extract ZIP into your SmartMartERP root.')

    previous = {file: file.read_text(encoding='utf-8') for file in [SETTINGS, URLS, BASE, ADMIN, STAFF, STOCK]}
    settings = previous[SETTINGS]
    if 'returns_ops.apps.ReturnsOpsConfig' not in settings or 'shift_ops.apps.ShiftOpsConfig' not in settings:
        stop('Stage 13B is not active. First run python repair_smartmart_stage13b.py and get its tests passing. No files changed.')
    if 'stock_alerts.apps.StockAlertsConfig' not in settings:
        pos = re.search(r'(?m)^\s*INSTALLED_APPS\s*=\s*\[\s*\n', settings)
        if not pos:
            stop('Cannot locate INSTALLED_APPS safely. No files changed.')
        settings = settings[:pos.end()] + "    'stock_alerts.apps.StockAlertsConfig',\n" + settings[pos.end():]

    urls = previous[URLS]
    if not re.search(r'\binclude\s*\(\s*[\'\"]stock_alerts\.urls[\'\"]\s*\)', urls):
        found = re.search(r'(?m)^from django\.urls import ([^\n]+)$', urls)
        if not found:
            stop('Cannot locate django.urls import safely. No files changed.')
        parts = [part.strip() for part in found.group(1).split(',')]
        for item in ['path', 'include']:
            if item not in parts:
                parts.append(item)
        urls = urls[:found.start()] + 'from django.urls import ' + ', '.join(parts) + urls[found.end():]
        found = re.search(r'(?m)^\s*urlpatterns\s*=\s*\[\s*\n', urls)
        if not found:
            stop('Cannot locate urlpatterns safely. No files changed.')
        urls = urls[:found.end()] + "    path('alerts/', include('stock_alerts.urls')),\n" + urls[found.end():]

    base = previous[BASE]
    if 'SMARTMART_STAGE13C_NAV' not in base:
        anchor = '<a class="nav-link" href="{% url \'core:dashboard\' %}">My workspace</a>'
        if anchor not in base:
            stop('Shared navigation differs from the expected layout. No files changed.')
        base = base.replace(anchor, anchor + '\n          <!-- SMARTMART_STAGE13C_NAV -->\n'
                            '          {% if user.is_superuser %}<a class="nav-link" href="{% url \'stock_alerts:home\' %}">Stock alerts</a>{% endif %}', 1)

    admin = previous[ADMIN]
    if 'SMARTMART_STAGE13C_ADMIN' not in admin:
        loc = admin.rfind('{% endblock %}')
        if loc == -1:
            stop('Administrator dashboard differs from expected layout. No files changed.')
        extra = ('\n<!-- SMARTMART_STAGE13C_ADMIN -->\n'
                 '<section class="wrap" style="padding:12px 0 36px"><div class="profile-strip">'
                 '<div><strong>Low-stock alerts &amp; reorder planner</strong>'
                 '<p>Prioritize branch replenishment, review stockouts, and download suggested order quantities.</p></div>'
                 '<a class="button button-primary" href="{% url \'stock_alerts:home\' %}">View stock alerts →</a>'
                 '</div></section>\n')
        admin = admin[:loc] + extra + admin[loc:]

    staff = previous[STAFF]
    if 'SMARTMART_STAGE13C_STAFF' not in staff:
        loc = staff.rfind('{% endblock %}')
        if loc == -1:
            stop('Staff dashboard differs from expected layout. No files changed.')
        extra = ('\n<!-- SMARTMART_STAGE13C_STAFF -->\n'
                 '{% if profile.role == "MANAGER" or profile.role == "WAREHOUSE" %}'
                 '<section class="wrap" style="padding:16px 0 36px"><div class="profile-strip">'
                 '<div><strong>Branch reorder alerts</strong>'
                 '<p>Review low stock, out-of-stock items and suggested reorder quantities at your branch.</p></div>'
                 '<a class="button button-primary" href="{% url \'stock_alerts:home\' %}">Stock alerts →</a>'
                 '</div></section>{% endif %}\n')
        staff = staff[:loc] + extra + staff[loc:]

    stock = previous[STOCK]
    if 'SMARTMART_STAGE13C_STOCK' not in stock:
        anchor = '<div class="inventory-actions">'
        if anchor not in stock:
            stop('Inventory stock page differs from expected layout. No files changed.')
        stock = stock.replace(anchor, anchor + '<!-- SMARTMART_STAGE13C_STOCK -->'
                              '<a class="button button-soft" href="{% url \'stock_alerts:home\' %}?branch={{ branch.pk }}">Low-stock alerts →</a>', 1)

    return previous, {SETTINGS: settings, URLS: urls, BASE: base, ADMIN: admin, STAFF: staff, STOCK: stock}


def install():
    print('SMARTMART ERP STAGE 13C — BRANCH LOW-STOCK ALERTS', flush=True)
    before, after = prepare()
    try:
        # This only uses a temporary Django test DB, not the live store DB.
        manage('test', 'shift_ops', '--noinput')
    except Exception as exc:
        stop('Stage 13B tests are not passing. Run python repair_smartmart_stage13b.py first. No configuration changed. Reason: ' + str(exc))

    try:
        from smartmart_backup import create_backup
        backup_dir = create_backup()
    except Exception as exc:
        stop('Verified private backup could not be created. No configuration changed. ' + str(exc))
    print('VERIFIED PRIVATE BACKUP:', backup_dir, flush=True)
    for file, contents in before.items():
        target = backup_dir / 'preinstall_files' / file.relative_to(ROOT)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(contents, encoding='utf-8')
    try:
        for file, contents in after.items():
            if contents != before[file]:
                file.write_text(contents, encoding='utf-8')
        manage('check')
        manage('test', 'stock_alerts', '--noinput')
    except Exception as exc:
        for file, contents in before.items():
            file.write_text(contents, encoding='utf-8')
        stop('Stage 13C checks failed. Original configuration restored. Database untouched. Backup: '
             + str(backup_dir) + '. Reason: ' + str(exc))
    print('\nSTAGE 13C INSTALLED SUCCESSFULLY. No migrations or inventory changes were made.')
    print('Open http://127.0.0.1:8002/alerts/ as an approved manager, warehouse staff or administrator.')
    print('NEXT: python manage.py test --noinput')
    print('Planning only. No supplier orders are submitted automatically.')


if __name__ == '__main__':
    install()
