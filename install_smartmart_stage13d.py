"""Install read-only Stage 13D reporting into a pre-existing SmartMart ERP.

Idempotent, no Django schema changes. Backs up live SQLite using the verified
project backup tool BEFORE editing config or templates. Restores edited files
if Django checks/new tests fail. Does not edit settings used by hosted staging.
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
APP = ROOT / 'reporting_insights'


def stop(text):
    raise SystemExit('STAGE 13D STOPPED SAFELY: ' + text)


def django(*args):
    print('RUNNING: python manage.py ' + ' '.join(args), flush=True)
    status = subprocess.run([sys.executable, str(ROOT / 'manage.py'), *args], cwd=ROOT, check=False)
    if status.returncode:
        raise RuntimeError('Django command exited with status ' + str(status.returncode))


def prepare():
    necessary = [ROOT / 'manage.py', ROOT / 'smartmart_backup.py', SETTINGS, URLS,
                 BASE, ADMIN, STAFF, ROOT / 'returns_ops' / 'models.py',
                 ROOT / 'shift_ops' / 'models.py', ROOT / 'stock_alerts' / 'apps.py',
                 ROOT / 'finance_ops' / 'models.py', APP / '__init__.py',
                 APP / 'apps.py', APP / 'services.py', APP / 'views.py',
                 APP / 'urls.py', APP / 'tests.py',
                 APP / 'templates' / 'reporting_insights' / 'home.html',
                 APP / 'static' / 'reporting_insights' / 'css' / 'reports.css']
    absent = [str(p.relative_to(ROOT)) for p in necessary if not p.is_file()]
    if absent:
        stop('Missing required files: ' + ', '.join(absent) + '. Extract the ZIP into the SmartMartERP project folder.')
    files = [SETTINGS, URLS, BASE, ADMIN, STAFF]
    previous = {p: p.read_text(encoding='utf-8') for p in files}
    settings = previous[SETTINGS]
    for app in ('returns_ops.apps.ReturnsOpsConfig', 'shift_ops.apps.ShiftOpsConfig', 'stock_alerts.apps.StockAlertsConfig'):
        if app not in settings:
            stop('Prerequisite ' + app + ' is not active. Finish Stage 13B and 13C first; no files were changed.')
    if 'reporting_insights.apps.ReportingInsightsConfig' not in settings:
        found = re.search(r'(?m)^\s*INSTALLED_APPS\s*=\s*\[\s*\n', settings)
        if not found:
            stop('Could not safely find INSTALLED_APPS. No files were changed.')
        settings = settings[:found.end()] + "    'reporting_insights.apps.ReportingInsightsConfig',\n" + settings[found.end():]

    urls = previous[URLS]
    if not re.search(r'\binclude\s*\(\s*[\'\"]reporting_insights\.urls[\'\"]\s*\)', urls):
        found = re.search(r'(?m)^from django\.urls import ([^\n]+)$', urls)
        if not found:
            stop('Could not safely locate URL imports. No files were changed.')
        parts = [part.strip() for part in found.group(1).split(',')]
        for item in ('path', 'include'):
            if item not in parts:
                parts.append(item)
        urls = urls[:found.start()] + 'from django.urls import ' + ', '.join(parts) + urls[found.end():]
        found = re.search(r'(?m)^\s*urlpatterns\s*=\s*\[\s*\n', urls)
        if not found:
            stop('Could not safely locate urlpatterns. No files were changed.')
        urls = urls[:found.end()] + "    path('insights/', include('reporting_insights.urls')),\n" + urls[found.end():]

    base = previous[BASE]
    if 'SMARTMART_STAGE13D_NAV' not in base:
        anchor = '<a class="nav-link" href="{% url \'core:dashboard\' %}">My workspace</a>'
        if anchor not in base:
            stop('The base navigation differs from the expected layout. No files were changed.')
        base = base.replace(anchor, anchor + '\n          <!-- SMARTMART_STAGE13D_NAV -->\n'
                            '          {% if user.is_superuser %}<a class="nav-link" href="{% url \'reporting_insights:home\' %}">Insights</a>{% endif %}', 1)

    admin = previous[ADMIN]
    if 'SMARTMART_STAGE13D_ADMIN' not in admin:
        position = admin.rfind('{% endblock %}')
        if position < 0:
            stop('Admin dashboard template is incompatible. No files were changed.')
        addition = ('\n<!-- SMARTMART_STAGE13D_ADMIN -->\n'
                    '<section class="wrap" style="padding:12px 0 36px"><div class="profile-strip">'
                    '<div><strong>Advanced management reports</strong>'
                    '<p>Confirmed sales, recorded refunds, approved expenses, estimated merchandise margin and inventory valuation.</p></div>'
                    '<a class="button button-primary" href="{% url \'reporting_insights:home\' %}">View reports →</a>'
                    '</div></section>\n')
        admin = admin[:position] + addition + admin[position:]

    staff = previous[STAFF]
    if 'SMARTMART_STAGE13D_STAFF' not in staff:
        position = staff.rfind('{% endblock %}')
        if position < 0:
            stop('Staff dashboard template is incompatible. No files were changed.')
        addition = ('\n<!-- SMARTMART_STAGE13D_STAFF -->\n'
                    '{% if profile.role == "MANAGER" %}<section class="wrap" style="padding:16px 0 36px">'
                    '<div class="profile-strip"><div><strong>Branch management reports</strong>'
                    '<p>Review confirmed sales, approved expenses, refunds and indicative margin at your assigned branch.</p></div>'
                    '<a class="button button-primary" href="{% url \'reporting_insights:home\' %}">Branch reports →</a>'
                    '</div></section>{% endif %}\n')
        staff = staff[:position] + addition + staff[position:]

    return previous, {SETTINGS: settings, URLS: urls, BASE: base, ADMIN: admin, STAFF: staff}


def install():
    print('SMARTMART ERP STAGE 13D — ADVANCED MANAGEMENT REPORTS', flush=True)
    before, after = prepare()
    try:
        django('test', 'stock_alerts', '--noinput')
    except Exception as exc:
        stop('Stage 13C tests must pass first. No files were changed. Reason: ' + str(exc))
    try:
        from smartmart_backup import create_backup
        directory = create_backup()
    except Exception as exc:
        stop('Verified private backup failed. No files were changed. Reason: ' + str(exc))
    print('VERIFIED PRIVATE BACKUP:', directory, flush=True)
    for file, content in before.items():
        destination = directory / 'preinstall_files' / file.relative_to(ROOT)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(content, encoding='utf-8')
    try:
        for file, content in after.items():
            if before[file] != content:
                file.write_text(content, encoding='utf-8')
        django('check')
        django('test', 'reporting_insights', '--noinput')
    except Exception as exc:
        for file, content in before.items():
            file.write_text(content, encoding='utf-8')
        stop('New report checks failed; original config and templates restored. '
             'Existing business records remain unchanged. Backup: ' + str(directory) + '. Reason: ' + str(exc))
    print('\nSTAGE 13D INSTALLED SUCCESSFULLY. No migrations or stock/sales edits.')
    print('Open http://127.0.0.1:8002/insights/ as administrator or approved branch manager.')
    print('NEXT: python manage.py test --noinput')
    print('Estimated merchandise margins use CURRENT costs, not historical accounting COGS.')


if __name__ == '__main__':
    install()
