"""Non-destructive Stage 13H membership, paid-receipt points and reward reservations.

Requires Stage 13G. Leaves the existing POS pricing/checkout, receipt values and
all historical business records unchanged. Backs up before migrating.
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
RECEIPT = ROOT / 'pos/templates/pos/receipt.html'
EDIT = (SETTINGS, URLS, BASE, ADMIN, STAFF, RECEIPT)
APP = ROOT / 'loyalty_ops'


def stop(message):
    raise SystemExit('STAGE 13H STOPPED SAFELY: ' + str(message))


def run_django(*args):
    print('RUNNING: python manage.py ' + ' '.join(args), flush=True)
    p = subprocess.run([sys.executable, str(ROOT / 'manage.py'), *args], cwd=ROOT)
    if p.returncode:
        raise RuntimeError('Django returned exit code ' + str(p.returncode))


def prepare():
    necessary = [ROOT / 'manage.py', ROOT / 'smartmart_backup.py',
                 ROOT / 'promotion_ops/tests.py', ROOT / 'returns_ops/models.py',
                 APP / 'models.py', APP / 'services.py', APP / 'views.py', APP / 'forms.py',
                 APP / 'tests.py', APP / 'urls.py', APP / 'migrations/0001_initial.py',
                 APP / 'templates/loyalty_ops/home.html',
                 APP / 'templates/loyalty_ops/member.html',
                 APP / 'templates/loyalty_ops/rewards.html',
                 APP / 'templates/loyalty_ops/enroll.html',
                 APP / 'static/loyalty_ops/css/loyalty.css', *EDIT]
    missing = [str(p.relative_to(ROOT)) for p in necessary if not p.exists()]
    if missing:
        raise ValueError('Missing files: ' + ', '.join(missing) + '. Extract Stage 13H ZIP into SmartMartERP.')
    before = {p: p.read_text(encoding='utf-8-sig') for p in EDIT}
    settings = before[SETTINGS]
    if 'promotion_ops.apps.PromotionOpsConfig' not in settings:
        raise ValueError('Stage 13G promotions is not yet active. Install and test it first.')
    if 'loyalty_ops.apps.LoyaltyOpsConfig' not in settings:
        settings, n = re.subn(r'(?m)^(\s*INSTALLED_APPS\s*=\s*\[\s*\n)',
            "\\g<1>    'loyalty_ops.apps.LoyaltyOpsConfig',\n", settings, count=1)
        if n != 1:
            raise ValueError('Cannot locate INSTALLED_APPS. No files changed.')
    urls = before[URLS]
    if "include('loyalty_ops.urls')" not in urls and 'include("loyalty_ops.urls")' not in urls:
        match = re.search(r'(?m)^from django.urls import [^\n]+$', urls)
        if not match:
            raise ValueError('Cannot locate Django URL imports.')
        if 'include' not in match.group(0):
            urls = urls.replace(match.group(0), match.group(0) + ', include', 1)
        urls, n = re.subn(r'(?m)^(\s*urlpatterns\s*=\s*\[\s*\n)',
            "\\g<1>    path('loyalty/', include('loyalty_ops.urls')),\n", urls, count=1)
        if n != 1:
            raise ValueError('Cannot locate urlpatterns list.')
    base = before[BASE]
    if '<!-- SMARTMART_STAGE13H_NAV -->' not in base:
        needle = '<a class="nav-link" href="{% url \'core:dashboard\' %}">My workspace</a>'
        if base.count(needle) != 1:
            raise ValueError('Unexpected navigation layout.')
        base = base.replace(needle, needle + '\n          <!-- SMARTMART_STAGE13H_NAV -->\n          {% if user.is_superuser or user.store_profile.is_approved and user.store_profile.role == "CASHIER" or user.store_profile.is_approved and user.store_profile.role == "MANAGER" %}<a class="nav-link" href="{% url \'loyalty_ops:home\' %}">Loyalty</a>{% endif %}', 1)
    admin = before[ADMIN]
    if '<!-- SMARTMART_STAGE13H_ADMIN -->' not in admin:
        i = admin.rfind('{% endblock %}')
        if i < 0:
            raise ValueError('Missing admin dashboard endblock.')
        admin = admin[:i] + '\n<!-- SMARTMART_STAGE13H_ADMIN -->\n<section class="wrap" style="padding:12px 0 24px"><div class="profile-strip"><div><strong>Loyalty &amp; Rewards</strong><p>Register members with consent, link paid receipts and review reward requests.</p></div><a class="button button-primary" href="{% url \'loyalty_ops:home\' %}">Manage loyalty →</a></div></section>\n' + admin[i:]
    staff = before[STAFF]
    if '<!-- SMARTMART_STAGE13H_STAFF -->' not in staff:
        i = staff.rfind('{% endblock %}')
        if i < 0:
            raise ValueError('Missing staff dashboard endblock.')
        staff = staff[:i] + '\n<!-- SMARTMART_STAGE13H_STAFF -->\n{% if profile.is_approved and profile.role == "MANAGER" or profile.is_approved and profile.role == "CASHIER" %}<section class="wrap" style="padding:12px 0 24px"><div class="profile-strip"><div><strong>Customer Loyalty</strong><p>Find members, link verified sales and reserve approved rewards.</p></div><a class="button button-primary" href="{% url \'loyalty_ops:home\' %}">Loyalty centre →</a></div></section>{% endif %}\n' + staff[i:]
    receipt = before[RECEIPT]
    if '<!-- SMARTMART_STAGE13H_RECEIPT -->' not in receipt:
        needle = '<div class="pos-receipt-actions no-print">'
        if receipt.count(needle) != 1:
            raise ValueError('Unexpected POS receipt layout.')
        receipt = receipt.replace(needle, '<!-- SMARTMART_STAGE13H_RECEIPT -->\n  <p class="no-print" style="margin:14px 0;color:#476254">Loyalty members: <a href="{% url \'loyalty_ops:home\' %}">open Loyalty Centre</a> to link this paid receipt (<strong>{{ sale.receipt_number }}</strong>) after customer consent. Unverified external payments are not eligible.</p>\n  ' + needle, 1)
    after = {SETTINGS: settings, URLS: urls, BASE: base, ADMIN: admin, STAFF: staff, RECEIPT: receipt}
    for path, content in after.items():
        if path.suffix == '.py':
            ast.parse(content, filename=str(path))
    return before, after


def main():
    print('SMARTMART ERP STAGE 13H — CUSTOMER LOYALTY & REWARDS', flush=True)
    try:
        before, after = prepare()
    except Exception as exc:
        stop(exc)
    try:
        run_django('test', 'promotion_ops', '--noinput')
    except Exception as exc:
        stop('Stage 13G promotion tests must pass before this installer modifies files. ' + str(exc))
    try:
        from smartmart_backup import create_backup
        backup = create_backup()
    except Exception as exc:
        stop('Private verified backup failed. No application files changed. ' + str(exc))
    print('VERIFIED PRIVATE BACKUP:', backup, flush=True)
    for path, original in before.items():
        to = backup / 'pre_stage13h_files' / path.relative_to(ROOT)
        to.parent.mkdir(parents=True, exist_ok=True)
        to.write_text(original, encoding='utf-8')
    try:
        for path, content in after.items():
            if before[path] != content:
                path.write_text(content, encoding='utf-8')
        run_django('check')
        run_django('migrate', 'loyalty_ops', '--noinput')
        run_django('test', 'loyalty_ops', '--noinput')
    except Exception as exc:
        for path, original in before.items():
            path.write_text(original, encoding='utf-8')
        stop('Original configuration and templates restored. Empty loyalty tables may remain after migration; no existing sales, stock or customer data were modified. Backup: ' + str(backup) + '. ' + str(exc))
    print('\nSTAGE 13H INSTALLED. Loyalty centre: http://127.0.0.1:8002/loyalty/', flush=True)
    print('No cash refunds, stock changes, POS price discounts or marketing messages are automated.')
    print('NEXT: python manage.py test --noinput', flush=True)


if __name__ == '__main__':
    main()
