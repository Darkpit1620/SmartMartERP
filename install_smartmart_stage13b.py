"""SmartMart ERP Stage 13B: non-destructive, repeatable cashier shift installer.

Requires repaired Stage 13A before adding new modules. Backs up and restores
configuration on error; migration creates only new shift_ops tables.
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
APP = ROOT / 'shift_ops'


def fail(message):
    raise SystemExit('STAGE 13B STOPPED SAFELY: ' + message)


def django(*args):
    print('RUNNING: python manage.py ' + ' '.join(args), flush=True)
    result = subprocess.run([sys.executable, str(ROOT / 'manage.py'), *args], cwd=ROOT, check=False)
    if result.returncode:
        raise RuntimeError('Django command failed with exit status ' + str(result.returncode))


def prepare():
    required = [
        SETTINGS, URLS, BASE, ADMIN, STAFF, ROOT / 'manage.py',
        ROOT / 'smartmart_backup.py', ROOT / 'pos' / 'models.py',
        ROOT / 'returns_ops' / 'tests.py',
        APP / 'apps.py', APP / 'models.py', APP / 'services.py',
        APP / 'views.py', APP / 'urls.py', APP / 'admin.py', APP / 'tests.py',
        APP / 'migrations' / '0001_initial.py',
        APP / 'templates' / 'shift_ops' / 'home.html',
        APP / 'templates' / 'shift_ops' / 'detail.html',
    ]
    missing = [str(p.relative_to(ROOT)) for p in required if not p.is_file()]
    if missing:
        fail('Missing files: ' + ', '.join(missing) + '. Extract package into the SmartMart project root.')
    previous = {p: p.read_text(encoding='utf-8') for p in (SETTINGS, URLS, BASE, ADMIN, STAFF)}
    cfg = previous[SETTINGS]
    if 'returns_ops.apps.ReturnsOpsConfig' not in cfg:
        fail('Stage 13A is not active. First run python repair_smartmart_stage13a.py and ensure its tests pass; no files changed.')
    if 'shift_ops.apps.ShiftOpsConfig' not in cfg:
        match = re.search(r'(?m)^\s*INSTALLED_APPS\s*=\s*\[\s*\n', cfg)
        if not match:
            fail('Cannot safely locate INSTALLED_APPS; no files changed.')
        cfg = cfg[:match.end()] + "    'shift_ops.apps.ShiftOpsConfig',\n" + cfg[match.end():]

    urls = previous[URLS]
    if not re.search(r'\binclude\s*\(\s*[\'\"]shift_ops\.urls[\'\"]\s*\)', urls):
        found = re.search(r'(?m)^from django\.urls import ([^\n]+)$', urls)
        if not found:
            fail('Cannot safely locate the django.urls import; no files changed.')
        imports = [word.strip() for word in found.group(1).split(',')]
        for word in ('path', 'include'):
            if word not in imports:
                imports.append(word)
        urls = urls[:found.start()] + 'from django.urls import ' + ', '.join(imports) + urls[found.end():]
        found = re.search(r'(?m)^\s*urlpatterns\s*=\s*\[\s*\n', urls)
        if not found:
            fail('Cannot safely locate urlpatterns; no files changed.')
        urls = urls[:found.end()] + "    path('shifts/', include('shift_ops.urls')),\n" + urls[found.end():]

    base = previous[BASE]
    if 'SMARTMART_STAGE13B_NAV' not in base:
        nav_anchor = '<a class="nav-link" href="{% url \'core:dashboard\' %}">My workspace</a>'
        if nav_anchor not in base:
            fail('Navigation layout has changed; no files changed.')
        base = base.replace(nav_anchor, nav_anchor + '\n          <!-- SMARTMART_STAGE13B_NAV -->\n'
                            '          {% if user.is_superuser %}<a class="nav-link" href="{% url \'shift_ops:home\' %}">Cashier shifts</a>{% endif %}', 1)

    admin = previous[ADMIN]
    if 'SMARTMART_STAGE13B_ADMIN' not in admin:
        idx = admin.rfind('{% endblock %}')
        if idx == -1:
            fail('Administrator template is not compatible; no files changed.')
        link = ('\n<!-- SMARTMART_STAGE13B_ADMIN -->\n'
                '<section class="wrap" style="padding:12px 0 36px"><div class="profile-strip">'
                '<div><strong>Cashier shift reconciliation</strong>'
                '<p>Opening floats, cash movements, counted cash, shortages and manager review.</p></div>'
                '<a class="button button-primary" href="{% url \'shift_ops:home\' %}">Manage cashier shifts →</a>'
                '</div></section>\n')
        admin = admin[:idx] + link + admin[idx:]

    staff = previous[STAFF]
    if 'SMARTMART_STAGE13B_STAFF' not in staff:
        idx = staff.rfind('{% endblock %}')
        if idx == -1:
            fail('Staff portal is not compatible; no files changed.')
        link = ('\n<!-- SMARTMART_STAGE13B_STAFF -->\n'
                '{% if profile.role == "CASHIER" or profile.role == "MANAGER" %}'
                '<section class="wrap" style="padding:18px 0 36px"><div class="profile-strip">'
                '<div><strong>Cashier shift management</strong>'
                '<p>{% if profile.role == "CASHIER" %}Count your opening float and close your drawer.'
                '{% else %}Review cash movements and shift variances for your branch.{% endif %}</p></div>'
                '<a class="button button-primary" href="{% url \'shift_ops:home\' %}">Open cashier shifts →</a>'
                '</div></section>{% endif %}\n')
        staff = staff[:idx] + link + staff[idx:]

    return previous, {SETTINGS: cfg, URLS: urls, BASE: base, ADMIN: admin, STAFF: staff}


def install():
    print('SMARTMART ERP STAGE 13B — CASHIER SHIFT RECONCILIATION', flush=True)
    before, after = prepare()
    try:
        from smartmart_backup import create_backup
        folder = create_backup()
    except Exception as exc:
        fail('Verified private backup failed. No configuration changed. ' + str(exc))
    print('VERIFIED PRIVATE BACKUP:', folder, flush=True)
    for file, contents in before.items():
        save_to = folder / 'preinstall_files' / file.relative_to(ROOT)
        save_to.parent.mkdir(parents=True, exist_ok=True)
        save_to.write_text(contents, encoding='utf-8')
    try:
        for file, contents in after.items():
            if contents != before[file]:
                file.write_text(contents, encoding='utf-8')
        django('check')
        django('migrate', 'shift_ops', '--noinput')
        django('test', 'returns_ops', 'shift_ops', '--noinput')
    except Exception as exc:
        for file, contents in before.items():
            file.write_text(contents, encoding='utf-8')
        fail('Tests or migration failed. Original configuration restored; newly migrated empty shift '
             'tables may remain, but existing business records were not modified. Private backup: '
             + str(folder) + '. Reason: ' + str(exc))
    print('\nSTAGE 13B INSTALLED. Existing POS/finance/return records remain unchanged.')
    print('Open http://127.0.0.1:8002/shifts/ with a cashier, manager or administrator account.')
    print('NEXT: python manage.py test --noinput')
    print('Note: POS does not yet require an open shift before checkout. Reconcile any cash sales outside a shift separately.')


if __name__ == '__main__':
    install()
