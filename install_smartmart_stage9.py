"""Additive SmartMart ERP Stage 9: live readiness page and verified private backup.

Run inside an existing Stage 8 SmartMartERP project, using the activated .venv:
    python install_smartmart_stage9.py

No existing model or business record is altered. Requires a valid SQLite database.
"""
from pathlib import Path
import re
import subprocess
import sys

from smartmart_backup import create_backup

ROOT = Path(__file__).resolve().parent
SETTINGS = ROOT / 'config' / 'settings.py'
URLS = ROOT / 'config' / 'urls.py'
BASE = ROOT / 'core' / 'templates' / 'core' / 'base.html'
ADMIN = ROOT / 'core' / 'templates' / 'core' / 'admin_portal.html'
GITIGNORE = ROOT / '.gitignore'


def fail(message):
    raise SystemExit('\nSTAGE 9 STOPPED: ' + message)


def manage(*args):
    print('\nRUNNING: python manage.py ' + ' '.join(args), flush=True)
    outcome = subprocess.run([sys.executable, str(ROOT / 'manage.py'), *args], cwd=ROOT, check=False)
    if outcome.returncode:
        fail('A Django check or test failed. Read the output. Your pre-install backup is safe; do not delete the database.')


def plan_changes():
    required = [ROOT / 'manage.py', SETTINGS, URLS, BASE, ADMIN,
                ROOT / 'core/models.py', ROOT / 'inventory/models.py', ROOT / 'pos/models.py',
                ROOT / 'trading/models.py', ROOT / 'transfers/models.py',
                ROOT / 'workforce/models.py', ROOT / 'finance_ops/models.py',
                ROOT / 'operations/views.py', ROOT / 'operations/tests.py']
    missing = [str(p.relative_to(ROOT)) for p in required if not p.is_file()]
    if missing:
        fail('Required file(s) missing: ' + ', '.join(missing) + '. Install the earlier stages first.')
    original = {p: p.read_text(encoding='utf-8') for p in (SETTINGS, URLS, BASE, ADMIN)}
    settings = original[SETTINGS]
    earlier = ('core.apps.CoreConfig', 'inventory.apps.InventoryConfig', 'pos.apps.PosConfig',
               'trading.apps.TradingConfig', 'transfers.apps.TransfersConfig',
               'workforce.apps.WorkforceConfig', 'finance_ops.apps.FinanceOpsConfig')
    if any(value not in settings for value in earlier):
        fail('Expected Stages 2–8 are not all installed in config/settings.py.')
    mark = re.search(r'(?m)^\s*INSTALLED_APPS\s*=\s*\[\s*\n', settings)
    if not mark:
        fail('Cannot safely identify INSTALLED_APPS. No files modified.')
    if 'operations.apps.OperationsConfig' not in settings:
        settings = settings[:mark.end()] + '    "operations.apps.OperationsConfig",\n' + settings[mark.end():]
    urls = original[URLS]
    if not re.search(r'(?m)^\s*urlpatterns\s*=\s*\[\s*\n', urls):
        fail('Cannot safely identify urlpatterns. No files modified.')
    import_line = re.search(r'(?m)^from django\.urls import ([^\n]+)$', urls)
    if not import_line:
        fail('Cannot safely identify django.urls imports. No files modified.')
    if not re.search(r'''\binclude\s*\(\s*["']operations\.urls["']\s*\)''', urls):
        names = [n.strip() for n in import_line.group(1).split(',')]
        for n in ('path', 'include'):
            if n not in names:
                names.append(n)
        urls = urls[:import_line.start()] + 'from django.urls import ' + ', '.join(names) + urls[import_line.end():]
        anchor = re.search(r'(?m)^\s*urlpatterns\s*=\s*\[\s*\n', urls)
        urls = urls[:anchor.end()] + '    path("operations/", include("operations.urls")),\n' + urls[anchor.end():]

    base = original[BASE]
    nav_anchor = '<a class="nav-link" href="{% url \'core:dashboard\' %}">My workspace</a>'
    if 'SMARTMART_OPERATIONS_NAV' not in base:
        if nav_anchor not in base:
            fail('Could not find the safe SmartMart navigation insertion point. No files modified.')
        nav = ('\n          <!-- SMARTMART_OPERATIONS_NAV -->\n'
               '          {% if user.is_superuser %}\n'
               '          <a class="nav-link" href="{% url \'operations:overview\' %}">System readiness</a>\n'
               '          {% endif %}')
        base = base.replace(nav_anchor, nav_anchor + nav, 1)

    admin = original[ADMIN]
    if 'SMARTMART_OPERATIONS_ADMIN' not in admin:
        mark_last = admin.rfind('{% endblock %}')
        if mark_last < 0:
            fail('Could not identify the administrator template block ending.')
        card = ('\n<!-- SMARTMART_OPERATIONS_ADMIN -->\n'
                '<section class="wrap" style="padding:18px 0 34px">'
                '<div class="profile-strip"><div><strong>System Readiness &amp; Backups</strong>'
                '<p>Check all branches, inventory, sales, unverified payments, and deployment settings.</p>'
                '</div><a class="button button-primary" href="{% url \'operations:overview\' %}">Run readiness review →</a>'
                '</div></section>\n')
        admin = admin[:mark_last] + card + admin[mark_last:]

    ignores = ("\n# SMARTMART_STAGE9_PRIVATE_DATA\n"
               "/db.sqlite3\n/db.sqlite3-*\n/media/\n/.venv/\n/.env\n/.env.*\n"
               "/SmartMart_Stage*_Backups/\n/SmartMart_*Backups/\n"
               "__pycache__/\n*.py[cod]\n")
    current_ignore = GITIGNORE.read_text(encoding='utf-8') if GITIGNORE.exists() else ''
    if 'SMARTMART_STAGE9_PRIVATE_DATA' not in current_ignore:
        current_ignore = current_ignore.rstrip('\n') + '\n' + ignores
    original[GITIGNORE] = GITIGNORE.read_text(encoding='utf-8') if GITIGNORE.exists() else ''
    changes = {SETTINGS: settings, URLS: urls, BASE: base, ADMIN: admin, GITIGNORE: current_ignore}
    return original, changes


def install():
    print('SMARTMART ERP · STAGE 9: FINAL INTEGRATION AND SAFETY', flush=True)
    original, changes = plan_changes()
    try:
        backup_location = create_backup()
    except Exception as exc:
        fail('The verified private database backup failed. No configuration files changed: ' + str(exc))
    print('PRIVATE VERIFIED BACKUP:', backup_location, flush=True)
    # Back up every template/configuration file before patching, including original empty .gitignore.
    code_backup = backup_location / 'preinstall_files'
    for path, value in original.items():
        target = code_backup / path.relative_to(ROOT)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(value, encoding='utf-8')
    for path, value in changes.items():
        if not path.exists() or value != original[path]:
            path.write_text(value, encoding='utf-8')
    manage('check')
    manage('test', 'operations', '--noinput')
    print('\nSTAGE 9 INSTALLED: System Readiness dashboard and private backup tool.')
    print('Now run: python manage.py test --noinput  (all project modules)')
    print('Also run: python manage.py check --deploy  (warnings expected on local development)')
    print('Start your site: python manage.py runserver 8002')
    print('Open Admin Workspace > System Readiness & Backups')
    print('Do NOT deploy to the public internet until all readiness items are resolved.')


if __name__ == '__main__':
    install()
