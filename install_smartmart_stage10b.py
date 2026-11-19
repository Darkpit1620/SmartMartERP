"""Safe, repeatable SmartMart ERP Stage 10B installer.

Installs employee activation views; no database model change, user reset or data seeding.
Requires the Stage 2 portals and Stage 9 backup utility.
"""
from __future__ import annotations

from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
SETTINGS = ROOT / 'config' / 'settings.py'
URLS = ROOT / 'config' / 'urls.py'
BASE = ROOT / 'core' / 'templates' / 'core' / 'base.html'
ADMIN = ROOT / 'core' / 'templates' / 'core' / 'admin_portal.html'
APP = ROOT / 'staff_activation'


def fail(reason):
    raise SystemExit('STAGE 10B STOPPED SAFELY: ' + reason)


def run(*args):
    print('RUNNING: python manage.py ' + ' '.join(args), flush=True)
    completed = subprocess.run([sys.executable, str(ROOT / 'manage.py'), *args], cwd=ROOT, check=False)
    if completed.returncode:
        fail('Django command failed. Original configuration and verified backup are available; do not delete or reset your data.')


def planned_edits():
    required = [
        ROOT / 'manage.py', SETTINGS, URLS, BASE, ADMIN,
        ROOT / 'core' / 'models.py', ROOT / 'core' / 'forms.py',
        ROOT / 'smartmart_backup.py',
        APP / 'urls.py', APP / 'views.py', APP / 'forms.py', APP / 'tests.py',
        APP / 'templates' / 'staff_activation' / 'home.html',
    ]
    missing = [str(p.relative_to(ROOT)) for p in required if not p.exists()]
    if missing:
        fail('Missing file(s): ' + ', '.join(missing) + '. Extract the complete ZIP into SmartMartERP (not CampusLMS).')

    original = {p: p.read_text(encoding='utf-8') for p in (SETTINGS, URLS, BASE, ADMIN)}
    settings = original[SETTINGS]
    if 'core.apps.CoreConfig' not in settings:
        fail('The Stage 2 SmartMart core app is not registered; nothing has been modified.')
    if 'staff_activation.apps.StaffActivationConfig' not in settings:
        match = re.search(r'(?m)^\s*INSTALLED_APPS\s*=\s*\[\s*\n', settings)
        if not match:
            fail('Cannot safely locate INSTALLED_APPS in config/settings.py; nothing modified.')
        settings = settings[:match.end()] + '    "staff_activation.apps.StaffActivationConfig",\n' + settings[match.end():]

    urls = original[URLS]
    if not re.search(r'\binclude\s*\(\s*[\'\"]staff_activation\.urls[\'\"]\s*\)', urls):
        match = re.search(r'(?m)^from django\.urls import ([^\n]+)$', urls)
        if not match:
            fail('Cannot locate django.urls imports; nothing modified.')
        items = [x.strip() for x in match.group(1).split(',')]
        for item in ('path', 'include'):
            if item not in items:
                items.append(item)
        urls = urls[:match.start()] + 'from django.urls import ' + ', '.join(items) + urls[match.end():]
        pattern = re.search(r'(?m)^\s*urlpatterns\s*=\s*\[\s*\n', urls)
        if not pattern:
            fail('Cannot locate urlpatterns; nothing modified.')
        urls = urls[:pattern.end()] + '    path("employees/", include("staff_activation.urls")),\n' + urls[pattern.end():]

    base = original[BASE]
    marker = '<a class="nav-link" href="{% url \'core:dashboard\' %}">My workspace</a>'
    if 'SMARTMART_STAGE10B_EMPLOYEE_NAV' not in base:
        if marker not in base:
            fail('Custom navigation does not match Stage 2; no files changed. Please send base.html for a tailored update.')
        addition = ('\n          <!-- SMARTMART_STAGE10B_EMPLOYEE_NAV -->\n'
                    '          {% if user.is_superuser %}<a class="nav-link" href="{% url \'staff_activation:home\' %}">Employees & Branches</a>{% endif %}')
        base = base.replace(marker, marker + addition, 1)

    if 'SMARTMART_STAGE10B_PASSWORD_NAV' not in base:
        if marker not in base:
            fail('Cannot locate shared navigation to add the password-change link; nothing changed.')
        base = base.replace(marker, marker +
            '\n          <!-- SMARTMART_STAGE10B_PASSWORD_NAV -->\n'
            '          <a class="nav-link" href="{% url \'staff_activation:change_password\' %}">Change password</a>', 1)

    admin = original[ADMIN]
    if 'SMARTMART_STAGE10B_EMPLOYEE_CARD' not in admin:
        loc = admin.rfind('{% endblock %}')
        if loc == -1:
            fail('Admin portal template lacks an endblock; no files changed.')
        card = ('\n<!-- SMARTMART_STAGE10B_EMPLOYEE_CARD -->\n'
                '<section class="wrap" style="padding:12px 0 36px"><div class="profile-strip">'
                '<div><strong>Employee & Branch Activation</strong>'
                '<p>Create staff accounts and branches, review pending approvals and activate workspaces.</p></div>'
                '<a class="button button-primary" href="{% url \'staff_activation:home\' %}">Manage employees & branches →</a>'
                '</div></section>\n')
        admin = admin[:loc] + card + admin[loc:]
    return original, {SETTINGS: settings, URLS: urls, BASE: base, ADMIN: admin}


def install():
    print('SMARTMART ERP — STAGE 10B: EMPLOYEE & BRANCH ACTIVATION', flush=True)
    original, updates = planned_edits()
    # The Stage 9 backup utility performs a checked SQLite backup outside the project.
    try:
        from smartmart_backup import create_backup
        saved = create_backup()
    except Exception as exc:
        fail('Verified database backup failed. No configuration was changed. ' + str(exc))
    print('VERIFIED PRIVATE BACKUP:', saved, flush=True)
    for path, contents in original.items():
        dest = saved / 'preinstall_files' / path.relative_to(ROOT)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(contents, encoding='utf-8')
    for path, text in updates.items():
        if original[path] != text:
            path.write_text(text, encoding='utf-8')
    run('check')
    run('test', 'staff_activation', '--noinput')
    print('\nSTAGE 10B INSTALLED. No employee accounts or inventory records have been changed.')
    print('Start: python manage.py runserver 8002')
    print('Administrator Workspace → Employees & Branches')
    print('Optional local training accounts: python manage.py setup_staff_demo')
    print('Full project tests: python manage.py test --noinput')
    print('Private backup:', saved)


if __name__ == '__main__':
    install()
