"""Stage 13F SmartMart read-only barcode/shelf-label printing installer.

Run in the SmartMartERP root after extracting the full Stage13F ZIP. Requires
13E to be active and its tests to pass. No migrations or business record writes.
Preserves original configuration/templates and independently backs up live data.
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
APP = ROOT / 'label_printing'
APP_CONFIG = 'label_printing.apps.LabelPrintingConfig'
FILES_TO_UPDATE = (SETTINGS, URLS, BASE, ADMIN, STAFF)


def stop(message):
    raise SystemExit('STAGE 13F STOPPED SAFELY: ' + str(message))


def run_django(*args):
    print('RUNNING: python manage.py ' + ' '.join(args), flush=True)
    result = subprocess.run([sys.executable, str(ROOT / 'manage.py'), *args], cwd=ROOT, check=False)
    if result.returncode:
        raise RuntimeError('Django command exited with status ' + str(result.returncode))


def prepare():
    required = [ROOT / 'manage.py', ROOT / 'smartmart_backup.py',
        ROOT / 'inventory' / 'models.py', ROOT / 'core' / 'models.py',
        ROOT / 'sales_documents' / 'tests.py',
        APP / '__init__.py', APP / 'apps.py', APP / 'barcodes.py',
        APP / 'services.py', APP / 'views.py', APP / 'urls.py', APP / 'tests.py',
        APP / 'templates' / 'label_printing' / 'home.html',
        APP / 'templates' / 'label_printing' / 'print.html',
        APP / 'templates' / 'label_printing' / 'error.html',
        APP / 'static' / 'label_printing' / 'css' / 'labels.css', *FILES_TO_UPDATE]
    missing = [str(path.relative_to(ROOT)) for path in required if not path.is_file()]
    if missing:
        stop('Missing files: ' + ', '.join(missing) + '. Extract the ZIP into your existing SmartMartERP project root.')
    original = {path: path.read_text(encoding='utf-8-sig') for path in FILES_TO_UPDATE}
    settings = original[SETTINGS]
    if 'sales_documents.apps.SalesDocumentsConfig' not in settings:
        stop('Stage 13E is not active. Finish installing Stage 13E and run its tests first. No files changed.')
    if APP_CONFIG not in settings:
        match = re.search(r'(?m)^\s*INSTALLED_APPS\s*=\s*\[\s*\n', settings)
        if not match:
            stop('Cannot safely locate INSTALLED_APPS in config/settings.py. No changes made.')
        settings = settings[:match.end()] + "    'label_printing.apps.LabelPrintingConfig',\n" + settings[match.end():]
    urls = original[URLS]
    if not re.search(r'\binclude\s*\(\s*[\'\"]label_printing\.urls[\'\"]\s*\)', urls):
        match = re.search(r'(?m)^from django\.urls import ([^\n]+)$', urls)
        if not match:
            stop('Cannot locate Django URL imports. No changes made.')
        names = [name.strip() for name in match.group(1).split(',')]
        for name in ('include', 'path'):
            if name not in names:
                names.append(name)
        urls = urls[:match.start()] + 'from django.urls import ' + ', '.join(names) + urls[match.end():]
        match = re.search(r'(?m)^\s*urlpatterns\s*=\s*\[\s*\n', urls)
        if not match:
            stop('Cannot locate urlpatterns. No changes made.')
        urls = urls[:match.end()] + "    path('labels/', include('label_printing.urls')),\n" + urls[match.end():]

    base = original[BASE]
    if 'SMARTMART_STAGE13F_NAV' not in base:
        anchor = '<a class="nav-link" href="{% url \'core:dashboard\' %}">My workspace</a>'
        if anchor not in base:
            stop('Unexpected base navigation layout. No changes made.')
        base = base.replace(anchor, anchor + '\n          <!-- SMARTMART_STAGE13F_NAV -->\n'
                            '          {% if user.is_superuser %}<a class="nav-link" href="{% url \'label_printing:home\' %}">Product labels</a>{% endif %}', 1)
    admin = original[ADMIN]
    if 'SMARTMART_STAGE13F_ADMIN' not in admin:
        i = admin.rfind('{% endblock %}')
        if i < 0:
            stop('Unexpected administrator portal template. No changes made.')
        block = ('\n<!-- SMARTMART_STAGE13F_ADMIN -->\n'
            '<section class="wrap" style="padding:12px 0 32px"><div class="profile-strip"><div>'
            '<strong>Product barcode &amp; shelf labels</strong>'
            '<p>Print Code 128 SKU labels and accurate shelf price tags from your verified product catalogue.</p></div>'
            '<a class="button button-primary" href="{% url \'label_printing:home\' %}">Print product labels →</a>'
            '</div></section>\n')
        admin = admin[:i] + block + admin[i:]
    staff = original[STAFF]
    if 'SMARTMART_STAGE13F_STAFF' not in staff:
        i = staff.rfind('{% endblock %}')
        if i < 0:
            stop('Unexpected staff portal template. No changes made.')
        block = ('\n<!-- SMARTMART_STAGE13F_STAFF -->\n'
            '{% if profile.role == "MANAGER" or profile.role == "WAREHOUSE" %}'
            '<section class="wrap" style="padding:12px 0 32px"><div class="profile-strip"><div>'
            '<strong>Product barcode &amp; shelf labels</strong>'
            '<p>Print price tags and scannable SKU labels. Products with no retail price are skipped.</p></div>'
            '<a class="button button-primary" href="{% url \'label_printing:home\' %}">Open label centre →</a>'
            '</div></section>{% endif %}\n')
        staff = staff[:i] + block + staff[i:]
    return original, {SETTINGS: settings, URLS: urls, BASE: base, ADMIN: admin, STAFF: staff}


def install():
    print('SMARTMART ERP STAGE 13F — BARCODE & SHELF PRICE TAGS', flush=True)
    original, updated = prepare()
    try:
        run_django('test', 'sales_documents', '--noinput')
    except Exception as exc:
        stop('Stage 13E receipt/invoice tests must pass before installing Stage 13F. Original project unchanged. ' + str(exc))
    try:
        from smartmart_backup import create_backup
        backup_dir = create_backup()
    except Exception as exc:
        stop('Verified private backup failed. Nothing installed. ' + str(exc))
    print('VERIFIED PRIVATE BACKUP:', backup_dir, flush=True)
    for path, contents in original.items():
        target = backup_dir / 'pre_stage13f_files' / path.relative_to(ROOT)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(contents, encoding='utf-8')
    try:
        for path, contents in updated.items():
            if original[path] != contents:
                path.write_text(contents, encoding='utf-8')
        run_django('check')
        run_django('test', 'label_printing', '--noinput')
    except Exception as exc:
        for path, contents in original.items():
            path.write_text(contents, encoding='utf-8')
        stop('Stage 13F installation failed and the original settings/routes/templates were restored. '
             'No schema or business data changes. Backup: ' + str(backup_dir) + '. Reason: ' + str(exc))
    print('\nSTAGE 13F INSTALLED SUCCESSFULLY.', flush=True)
    print('Read-only feature; no database migration or inventory changes.')
    print('Open http://127.0.0.1:8002/labels/')
    print('Run all tests: python manage.py test --noinput')


if __name__ == '__main__':
    install()
