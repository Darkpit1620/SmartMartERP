"""Non-destructive installer for Stage 13E printable receipts and invoices.

Requires Stage 13D to pass first. Performs verified private SQLite/media backup
before editing installed settings/templates and executing migration/tests.
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
POS_RECEIPT = ROOT / 'pos' / 'templates' / 'pos' / 'receipt.html'
APP = ROOT / 'sales_documents'
APP_CONFIG = 'sales_documents.apps.SalesDocumentsConfig'


def stop(msg):
    raise SystemExit('STAGE 13E STOPPED SAFELY: ' + str(msg))


def django(*args):
    print('RUNNING: python manage.py ' + ' '.join(args), flush=True)
    p = subprocess.run([sys.executable, str(ROOT / 'manage.py'), *args], cwd=ROOT, check=False)
    if p.returncode:
        raise RuntimeError('Django command exited with status ' + str(p.returncode))


def prepare():
    required = [ROOT / 'manage.py', ROOT / 'smartmart_backup.py', SETTINGS, URLS, BASE, ADMIN,
        STAFF, POS_RECEIPT, ROOT / 'pos' / 'models.py', ROOT / 'pos' / 'permissions.py',
        ROOT / 'reporting_insights' / 'tests.py', APP / 'models.py', APP / 'apps.py',
        APP / 'forms.py', APP / 'views.py', APP / 'urls.py', APP / 'tests.py',
        APP / 'migrations' / '0001_initial.py',
        APP / 'templates' / 'sales_documents' / 'home.html',
        APP / 'templates' / 'sales_documents' / 'thermal.html',
        APP / 'templates' / 'sales_documents' / 'invoice.html',
        APP / 'templates' / 'sales_documents' / 'branding.html',
        APP / 'templates' / 'sales_documents' / 'customer.html',
        APP / 'static' / 'sales_documents' / 'css' / 'documents.css']
    missing = [str(f.relative_to(ROOT)) for f in required if not f.is_file()]
    if missing:
        stop('Missing files: ' + ', '.join(missing) + '. Extract Stage 13E ZIP into SmartMartERP first.')

    paths = (SETTINGS, URLS, BASE, ADMIN, STAFF, POS_RECEIPT)
    original = {file: file.read_text(encoding='utf-8-sig') for file in paths}
    source = original[SETTINGS]
    if 'reporting_insights.apps.ReportingInsightsConfig' not in source:
        stop('Stage 13D is not active. Finish the Stage 13D CSV repair and installer first; no changes made.')
    if APP_CONFIG not in source:
        match = re.search(r'(?m)^\s*INSTALLED_APPS\s*=\s*\[\s*\n', source)
        if not match:
            stop('Cannot identify INSTALLED_APPS safely. No changes made.')
        source = source[:match.end()] + "    'sales_documents.apps.SalesDocumentsConfig',\n" + source[match.end():]
    urls = original[URLS]
    if not re.search(r'\binclude\s*\(\s*[\'\"]sales_documents\.urls[\'\"]\s*\)', urls):
        match = re.search(r'(?m)^from django\.urls import ([^\n]+)$', urls)
        if not match:
            stop('Cannot identify django.urls imports. No changes made.')
        parts = [v.strip() for v in match.group(1).split(',')]
        for name in ('include', 'path'):
            if name not in parts:
                parts.append(name)
        urls = urls[:match.start()] + 'from django.urls import ' + ', '.join(parts) + urls[match.end():]
        match = re.search(r'(?m)^\s*urlpatterns\s*=\s*\[\s*\n', urls)
        if not match:
            stop('Cannot identify urlpatterns safely. No changes made.')
        urls = urls[:match.end()] + "    path('documents/', include('sales_documents.urls')),\n" + urls[match.end():]

    base = original[BASE]
    if 'SMARTMART_STAGE13E_NAV' not in base:
        anchor = '<a class="nav-link" href="{% url \'core:dashboard\' %}">My workspace</a>'
        if anchor not in base:
            stop('Unexpected core/base.html navigation. No changes made.')
        base = base.replace(anchor, anchor + '\n          <!-- SMARTMART_STAGE13E_NAV -->\n'
            "          {% if user.is_superuser %}<a class=\"nav-link\" href=\"{% url 'sales_documents:home' %}\">Print centre</a>{% endif %}", 1)

    admin = original[ADMIN]
    if 'SMARTMART_STAGE13E_ADMIN' not in admin:
        end = admin.rfind('{% endblock %}')
        if end < 0:
            stop('Unexpected admin portal template. No changes made.')
        snippet = ('\n<!-- SMARTMART_STAGE13E_ADMIN -->\n'
            '<section class="wrap" style="padding:16px 0 36px"><div class="profile-strip"><div><strong>Receipts and commercial invoices</strong>'
            '<p>Print clean 80mm POS receipts, non-fiscal A4 commercial invoices, and manage branch document branding.</p></div>'
            "<a class=\"button button-primary\" href=\"{% url 'sales_documents:home' %}\">Open print centre →</a>"
            '</div></section>\n')
        admin = admin[:end] + snippet + admin[end:]

    staff = original[STAFF]
    if 'SMARTMART_STAGE13E_STAFF' not in staff:
        end = staff.rfind('{% endblock %}')
        if end < 0:
            stop('Unexpected staff portal template. No changes made.')
        snippet = ('\n<!-- SMARTMART_STAGE13E_STAFF -->\n'
            '{% if profile.role == "MANAGER" or profile.role == "CASHIER" %}'
            '<section class="wrap" style="padding:16px 0 36px"><div class="profile-strip"><div>'
            '<strong>Printable sales documents</strong><p>Print receipts or commercial invoices from completed sales.</p></div>'
            "<a class=\"button button-primary\" href=\"{% url 'sales_documents:home' %}\">Print centre →</a>"
            '</div></section>{% endif %}\n')
        staff = staff[:end] + snippet + staff[end:]

    receipt = original[POS_RECEIPT]
    if 'SMARTMART_STAGE13E_POS_LINKS' not in receipt:
        anchor = '<div class="pos-receipt-actions no-print">'
        if anchor not in receipt:
            stop('Unexpected POS receipt actions. No changes made.')
        links = ('<!-- SMARTMART_STAGE13E_POS_LINKS -->'
            "<a class=\"button button-soft\" href=\"{% url 'sales_documents:thermal_receipt' sale.pk %}\">80mm print</a>"
            "<a class=\"button button-soft\" href=\"{% url 'sales_documents:commercial_invoice' sale.pk %}\">Commercial invoice</a>"
            "<a class=\"button button-soft\" href=\"{% url 'sales_documents:customer_details' sale.pk %}\">Customer details</a>")
        receipt = receipt.replace(anchor, anchor + links, 1)

    updated = {SETTINGS: source, URLS: urls, BASE: base, ADMIN: admin,
               STAFF: staff, POS_RECEIPT: receipt}
    return original, updated


def install():
    print('SMARTMART ERP STAGE 13E — RECEIPTS AND COMMERCIAL INVOICES', flush=True)
    original, updated = prepare()
    try:
        django('test', 'reporting_insights', '--noinput')
    except Exception as exc:
        stop('Stage 13D tests must pass first. If CSV formatting fails, run '
             'python repair_smartmart_stage13d.py. No configuration was changed. ' + str(exc))

    try:
        from smartmart_backup import create_backup
        backup_dir = create_backup()
    except Exception as exc:
        stop('Private verified backup failed; no configuration changed. ' + str(exc))
    print('VERIFIED PRIVATE BACKUP:', backup_dir, flush=True)
    for path, content in original.items():
        snapshot = backup_dir / 'pre_stage13e_files' / path.relative_to(ROOT)
        snapshot.parent.mkdir(parents=True, exist_ok=True)
        snapshot.write_text(content, encoding='utf-8')

    try:
        for path, content in updated.items():
            if original[path] != content:
                path.write_text(content, encoding='utf-8')
        django('check')
        django('migrate', 'sales_documents', '--noinput')
        django('makemigrations', 'sales_documents', '--check', '--dry-run')
        django('test', 'sales_documents', '--noinput')
    except Exception as exc:
        for path, content in original.items():
            path.write_text(content, encoding='utf-8')
        stop('Installation failed; previous configuration and POS receipt template restored. '
             'The new empty tables may remain after migration; existing business data is preserved. '
             'Private backup: ' + str(backup_dir) + '. Reason: ' + str(exc))

    print('\nSTAGE 13E INSTALLED SUCCESSFULLY.', flush=True)
    print('Receipt number and sale totals remain unchanged; new optional document tables created.')
    print('Open http://127.0.0.1:8002/documents/')
    print('Run full suite: python manage.py test --noinput')
    print('These are ordinary sales documents, NOT KRA eTIMS fiscal invoices.')


if __name__ == '__main__':
    install()
