"""Install Stage 13A return/refund records into existing SmartMartERP.

Backs up live SQLite, preserves existing sale history and settings, and uses
idempotent configuration edits. No demo data, automatic refunds or adjustments.
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
RECEIPT = ROOT / 'pos' / 'templates' / 'pos' / 'receipt.html'
APP = ROOT / 'returns_ops'


def fail(msg):
    raise SystemExit('STAGE 13A STOPPED SAFELY: ' + msg)


def cmd(*args):
    print('RUNNING: python manage.py ' + ' '.join(args), flush=True)
    r = subprocess.run([sys.executable, str(ROOT / 'manage.py'), *args], cwd=ROOT, check=False)
    if r.returncode:
        raise RuntimeError('Django command failed. Review the output above. Exit status ' + str(r.returncode))


def edits():
    required = [SETTINGS, URLS, BASE, ADMIN, RECEIPT, ROOT / 'smartmart_backup.py',
                ROOT / 'pos' / 'models.py', ROOT / 'inventory' / 'services.py',
                APP / 'models.py', APP / 'services.py', APP / 'views.py', APP / 'urls.py',
                APP / 'migrations' / '0001_initial.py', APP / 'tests.py',
                APP / 'templates' / 'returns_ops' / 'home.html',
                APP / 'templates' / 'returns_ops' / 'new.html',
                APP / 'templates' / 'returns_ops' / 'detail.html']
    missing = [str(p.relative_to(ROOT)) for p in required if not p.is_file()]
    if missing:
        fail('Missing prerequisites: ' + ', '.join(missing) + '. Extract into SmartMartERP project root.')
    orig = {p: p.read_text(encoding='utf-8') for p in (SETTINGS, URLS, BASE, ADMIN, RECEIPT)}
    settings = orig[SETTINGS]
    if 'pos.apps.PosConfig' not in settings and '"pos"' not in settings and "'pos'" not in settings:
        fail('POS app registration not found. No files changed.')
    if 'returns_ops.apps.ReturnsOpsConfig' not in settings:
        m = re.search(r'(?m)^\s*INSTALLED_APPS\s*=\s*\[\s*\n', settings)
        if not m:
            fail('Cannot locate INSTALLED_APPS list. No files changed.')
        settings = settings[:m.end()] + "    'returns_ops.apps.ReturnsOpsConfig',\n" + settings[m.end():]

    urls = orig[URLS]
    if not re.search(r'\binclude\s*\(\s*[\'\"]returns_ops\.urls[\'\"]\s*\)', urls):
        m = re.search(r'(?m)^from django\.urls import ([^\n]+)$', urls)
        if not m:
            fail('Cannot locate django.urls import. No files changed.')
        items = [x.strip() for x in m.group(1).split(',')]
        for entry in ('path', 'include'):
            if entry not in items:
                items.append(entry)
        urls = urls[:m.start()] + 'from django.urls import ' + ', '.join(items) + urls[m.end():]
        m = re.search(r'(?m)^\s*urlpatterns\s*=\s*\[\s*\n', urls)
        if not m:
            fail('Cannot locate urlpatterns list. No files changed.')
        urls = urls[:m.end()] + "    path('returns/', include('returns_ops.urls')),\n" + urls[m.end():]

    base = orig[BASE]
    if 'SMARTMART_STAGE13A_NAV' not in base:
        marker = '<a class="nav-link" href="{% url \'core:dashboard\' %}">My workspace</a>'
        if marker not in base:
            fail('Shared navbar differs from known SmartMart layout. No files changed.')
        extra = ('\n          <!-- SMARTMART_STAGE13A_NAV -->\n'
                 '          {% if user.is_superuser %}<a class="nav-link" href="{% url \'returns_ops:home\' %}">Returns</a>{% endif %}')
        base = base.replace(marker, marker + extra, 1)

    admin = orig[ADMIN]
    if 'SMARTMART_STAGE13A_ADMIN' not in admin:
        loc = admin.rfind('{% endblock %}')
        if loc == -1:
            fail('Administrator template cannot be located. No files changed.')
        card = ('\n<!-- SMARTMART_STAGE13A_ADMIN -->\n'
                '<section class="wrap" style="padding:12px 0 36px"><div class="profile-strip">'
                '<div><strong>Returns &amp; Refund Records</strong>'
                '<p>Review receipts, approve returns, audit restocking, and record verified offline refunds.</p></div>'
                '<a class="button button-primary" href="{% url \'returns_ops:home\' %}">Manage returns →</a>'
                '</div></section>\n')
        admin = admin[:loc] + card + admin[loc:]

    receipt = orig[RECEIPT]
    if 'SMARTMART_STAGE13A_RECEIPT' not in receipt:
        marker = '<div class="pos-receipt-actions no-print">'
        if marker not in receipt:
            fail('POS receipt template differs from known SmartMart layout. No files changed.')
        # Insert a separate and visible return action without rewriting receipt rendering.
        extra = ('<!-- SMARTMART_STAGE13A_RECEIPT -->\n'
                 '<div class="wrap no-print" style="padding:10px 0">'
                 '<a class="button button-soft" href="{% url \'returns_ops:new\' sale.pk %}">Request return from this receipt</a>'
                 '</div>\n')
        receipt = receipt.replace(marker, extra + marker, 1)
    return orig, {SETTINGS: settings, URLS: urls, BASE: base, ADMIN: admin, RECEIPT: receipt}


def install():
    print('SMARTMART ERP STAGE 13A — SALES RETURNS AND REFUND RECORDS', flush=True)
    old, updated = edits()
    try:
        from smartmart_backup import create_backup
        saved = create_backup()
    except Exception as exc:
        fail('Verified backup failed. Configuration untouched. ' + str(exc))
    print('VERIFIED PRIVATE BACKUP:', saved, flush=True)
    for path, contents in old.items():
        dest = saved / 'preinstall_files' / path.relative_to(ROOT)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(contents, encoding='utf-8')
    try:
        for path, contents in updated.items():
            if old[path] != contents:
                path.write_text(contents, encoding='utf-8')
        cmd('check')
        cmd('migrate', 'returns_ops', '--noinput')
        cmd('test', 'returns_ops', '--noinput')
    except Exception as exc:
        # Restore original configuration and templates; database backup also exists.
        for path, contents in old.items():
            path.write_text(contents, encoding='utf-8')
        fail('Installation/test failed; original configuration restored. New app tables may have been migrated, '
             'but no existing business data was changed. Backup: ' + str(saved) + '. Reason: ' + str(exc))
    print('\nSTAGE 13A INSTALLED. Existing sales and product data preserved.')
    print('Open http://127.0.0.1:8002/returns/ or a receipt → Request return.')
    print('Run full suite: python manage.py test --noinput')
    print('This does NOT process payouts or automatically adjust finance reports.')


if __name__ == '__main__':
    install()
