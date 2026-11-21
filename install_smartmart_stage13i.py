"""SmartMart ERP Stage 13I supplier-invoice ledger installer.

Non-destructive, repeatable: creates a verified private backup, edits only
five existing configuration/template files, creates new supplier-account tables,
and rolls the five files back if Django tests fail. No stock/sales mutations.
"""
import ast
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
SETTINGS = ROOT / 'config/settings.py'
URLS = ROOT / 'config/urls.py'
BASE = ROOT / 'core/templates/core/base.html'
ADMIN = ROOT / 'core/templates/core/admin_portal.html'
STAFF = ROOT / 'core/templates/core/staff_portal.html'
TRADE = ROOT / 'trading/templates/trading/home.html'
FILES = (SETTINGS, URLS, BASE, ADMIN, STAFF, TRADE)
APP = ROOT / 'supplier_accounts'
DISABLED_TESTS = APP / 'tests.py.stage13i_disabled'
LIVE_TESTS = APP / 'tests.py'


def stop(reason):
    raise SystemExit('STAGE 13I STOPPED SAFELY: ' + str(reason))


def run(*parts):
    print('RUNNING: python manage.py ' + ' '.join(parts), flush=True)
    p = subprocess.run([sys.executable, str(ROOT / 'manage.py'), *parts], cwd=ROOT, check=False)
    if p.returncode:
        raise RuntimeError('Django command returned exit status ' + str(p.returncode))


def prepare():
    required = [ROOT / 'manage.py', ROOT / 'smartmart_backup.py',
                ROOT / 'trading/models.py', ROOT / 'trading/migrations/0001_initial.py',
                APP / 'models.py', APP / 'services.py', APP / 'forms.py', APP / 'views.py',
                APP / 'urls.py', APP / 'permissions.py', APP / 'admin.py', APP / 'apps.py',
                APP / 'migrations/0001_initial.py',
                APP / 'templates/supplier_accounts/home.html',
                APP / 'templates/supplier_accounts/detail.html',
                APP / 'templates/supplier_accounts/form.html',
                APP / 'static/supplier_accounts/css/accounts.css', *FILES]
    if not LIVE_TESTS.exists() and not DISABLED_TESTS.exists():
        required.append(LIVE_TESTS)
    missing = [str(path.relative_to(ROOT)) for path in required if not path.exists()]
    if missing:
        raise ValueError('Missing files: ' + ', '.join(missing) + '. Extract the Stage 13I ZIP into your SmartMartERP root.')
    original = {path: path.read_text(encoding='utf-8-sig') for path in FILES}
    settings = original[SETTINGS]
    if 'trading.apps.TradingConfig' not in settings:
        raise ValueError('Existing Stage 5 supplier purchasing is not active. No files changed.')
    if 'supplier_accounts.apps.SupplierAccountsConfig' not in settings:
        settings, count = re.subn(r'(?m)^(\s*INSTALLED_APPS\s*=\s*\[\s*\n)',
                                  "\\g<1>    'supplier_accounts.apps.SupplierAccountsConfig',\n", settings, count=1)
        if count != 1:
            raise ValueError('Unable to locate INSTALLED_APPS. No files changed.')
    urls = original[URLS]
    if not re.search(r'\binclude\s*\(\s*[\'\"]supplier_accounts\.urls[\'\"]\s*\)', urls):
        found = re.search(r'(?m)^from django\.urls import ([^\n]+)$', urls)
        if not found:
            raise ValueError('Could not locate django.urls import. No files changed.')
        parts = [part.strip() for part in found.group(1).split(',')]
        for part in ('path', 'include'):
            if part not in parts:
                parts.append(part)
        urls = urls[:found.start()] + 'from django.urls import ' + ', '.join(parts) + urls[found.end():]
        urls, count = re.subn(r'(?m)^(\s*urlpatterns\s*=\s*\[\s*\n)',
                              "\\g<1>    path('supplier-accounts/', include('supplier_accounts.urls')),\n", urls, count=1)
        if count != 1:
            raise ValueError('Could not locate urlpatterns. No files changed.')

    base = original[BASE]
    if '<!-- SMARTMART_STAGE13I_NAV -->' not in base:
        needle = '<a class="nav-link" href="{% url \'core:dashboard\' %}">My workspace</a>'
        if base.count(needle) != 1:
            raise ValueError('Shared navigation differs from expected layout. No changes made.')
        base = base.replace(needle, needle + '\n          <!-- SMARTMART_STAGE13I_NAV -->\n'
            '          {% if user.is_superuser or user.store_profile.is_approved and user.store_profile.role == "MANAGER" %}<a class="nav-link" href="{% url \'supplier_accounts:home\' %}">Supplier accounts</a>{% endif %}', 1)

    admin = original[ADMIN]
    if '<!-- SMARTMART_STAGE13I_ADMIN -->' not in admin:
        i = admin.rfind('{% endblock %}')
        if i < 0:
            raise ValueError('Missing administrator template block. No changes made.')
        admin = admin[:i] + '\n<!-- SMARTMART_STAGE13I_ADMIN -->\n<section class="wrap" style="padding:12px 0 24px"><div class="profile-strip"><div><strong>Supplier invoices &amp; payments</strong><p>Record genuine supplier bills and paid payment references, and review outstanding balances by branch.</p></div><a class="button button-primary" href="{% url \'supplier_accounts:home\' %}">Supplier accounts →</a></div></section>\n' + admin[i:]

    staff = original[STAFF]
    if '<!-- SMARTMART_STAGE13I_STAFF -->' not in staff:
        i = staff.rfind('{% endblock %}')
        if i < 0:
            raise ValueError('Missing staff dashboard template block. No changes made.')
        staff = staff[:i] + '\n<!-- SMARTMART_STAGE13I_STAFF -->\n{% if profile.is_approved and profile.role == "MANAGER" %}<section class="wrap" style="padding:12px 0 24px"><div class="profile-strip"><div><strong>Supplier invoices &amp; payments</strong><p>View branch liabilities and record payments that were actually completed.</p></div><a class="button button-primary" href="{% url \'supplier_accounts:home\' %}">Supplier accounts →</a></div></section>{% endif %}\n' + staff[i:]

    trade = original[TRADE]
    if '<!-- SMARTMART_STAGE13I_TRADE -->' not in trade:
        i = trade.rfind('{% endblock %}')
        if i < 0:
            raise ValueError('Missing supplier-purchasing page block. No changes made.')
        trade = trade[:i] + '\n<!-- SMARTMART_STAGE13I_TRADE -->\n{% if can_purchase %}<section class="tr-panel"><h2>Supplier Accounts</h2><p>Record supplier invoice numbers, reconcile outstanding amounts, and document actual payments without altering purchase receipts.</p><a class="button button-primary" href="{% url \'supplier_accounts:home\' %}{% if branch %}?branch={{ branch.pk }}{% endif %}">Open supplier accounts →</a></section>{% endif %}\n' + trade[i:]

    modified = {SETTINGS: settings, URLS: urls, BASE: base, ADMIN: admin, STAFF: staff, TRADE: trade}
    for path, content in modified.items():
        if path.suffix == '.py':
            ast.parse(content, filename=str(path))
    return original, modified


def install():
    print('SMARTMART ERP STAGE 13I — SUPPLIER INVOICES AND OUTSTANDING BALANCES', flush=True)
    try:
        before, after = prepare()
    except Exception as exc:
        stop(exc)
    # Run existing purchasing tests without modifying configuration or the real DB.
    try:
        run('test', 'trading', '--noinput')
        if 'loyalty_ops.apps.LoyaltyOpsConfig' in before[SETTINGS]:
            run('test', 'loyalty_ops', '--noinput')
        else:
            print('INFO: Stage 13H not active; this independent supplier ledger can still be installed.', flush=True)
    except Exception as exc:
        stop('Existing module checks did not pass; configuration unchanged. ' + str(exc))
    try:
        from smartmart_backup import create_backup
        backup = create_backup()
    except Exception as exc:
        stop('Private verified backup failed; configuration unchanged. ' + str(exc))
    print('VERIFIED PRIVATE BACKUP:', backup, flush=True)
    for path, content in before.items():
        target = backup / 'pre_stage13i_files' / path.relative_to(ROOT)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding='utf-8')
    try:
        if not LIVE_TESTS.exists() and DISABLED_TESTS.exists():
            DISABLED_TESTS.rename(LIVE_TESTS)
        for path, content in after.items():
            if content != before[path]:
                path.write_text(content, encoding='utf-8')
        run('check')
        run('migrate', 'supplier_accounts', '--noinput')
        run('test', 'supplier_accounts', '--noinput')
    except Exception as exc:
        for path, content in before.items():
            path.write_text(content, encoding='utf-8')
        # Avoid breaking a subsequent full test discovery if the app is no longer registered.
        if 'supplier_accounts.apps.SupplierAccountsConfig' not in before[SETTINGS] and LIVE_TESTS.exists():
            LIVE_TESTS.rename(DISABLED_TESTS)
        stop('Existing configuration restored. New empty ledger tables may remain, but existing supplier, stock and payment records were not modified. Backup: ' + str(backup) + '. ' + str(exc))
    print('\nSTAGE 13I INSTALLED. Open: http://127.0.0.1:8002/supplier-accounts/', flush=True)
    print('This ledger records confirmations only; it cannot transfer money or change inventory.')
    print('NEXT: python manage.py test --noinput', flush=True)


if __name__ == '__main__':
    install()
