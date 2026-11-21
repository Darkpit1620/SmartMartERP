"""Safe Stage 13I repair for SmartMart ERP (run from existing project root).

Patches test fixtures/assertions only, backs up the live database with
SmartMart's verified backup function, then reruns the original Stage 13I
installer and (on success) the full Django test suite. No business service,
model, migration, checkout, price, stock or payment logic is rewritten.
"""
import ast
import hashlib
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
SETTINGS = ROOT / 'config' / 'settings.py'
SUPPLIER = ROOT / 'supplier_accounts' / 'tests.py'
SUPPLIER_DISABLED = ROOT / 'supplier_accounts' / 'tests.py.stage13i_disabled'
INVENTORY = ROOT / 'inventory' / 'tests.py'
LOYALTY = ROOT / 'loyalty_ops' / 'tests.py'
INSTALLER = ROOT / 'install_smartmart_stage13i.py'

OLD_FIXTURE = "retail_price=Decimal('150.00'), cost_price=Decimal('100.00'))"
NEW_FIXTURE = "retail_price=Decimal('150.00'), wholesale_price=Decimal('130.00'), cost_price=Decimal('100.00'))"
OLD_STOCK_ASSERTION = 'self.assertNotContains(result, "40")'
NEW_STOCK_ASSERTION = 'self.assertNotContains(result, "<td><strong>40</strong></td>")'
GUARD_MARKER = '# SMARTMART_STAGE13I_OPTIONAL_LOYALTY_TEST_GUARD'
GUARD = '''\n# SMARTMART_STAGE13I_OPTIONAL_LOYALTY_TEST_GUARD
# During a failed Stage 13H installation, settings are rolled back but the
# source folder can remain. Skip its tests only while the app is not installed.
import unittest as _smartmart_unittest
from django.conf import settings as _smartmart_settings
if not any(entry == 'loyalty_ops' or entry.startswith('loyalty_ops.')
           for entry in _smartmart_settings.INSTALLED_APPS):
    raise _smartmart_unittest.SkipTest(
        'Optional Stage 13H loyalty app is inactive; its tests require installation.')

'''


def fail(message):
    raise SystemExit('STAGE 13I REPAIR STOPPED: ' + str(message))


def need_file(path):
    if not path.is_file():
        fail('Missing ' + str(path.relative_to(ROOT)) + '. Extract the original Stage 13I ZIP first.')


def sha(data):
    return hashlib.sha256(data).hexdigest()


def updated_content():
    for path in (ROOT / 'manage.py', ROOT / 'db.sqlite3', ROOT / 'smartmart_backup.py',
                 SETTINGS, INVENTORY, INSTALLER):
        need_file(path)
    supplier = SUPPLIER if SUPPLIER.is_file() else SUPPLIER_DISABLED
    need_file(supplier)
    if not (ROOT / 'supplier_accounts' / 'models.py').is_file():
        fail('Stage 13I supplier_accounts source files are missing.')
    changes = {}

    old = supplier.read_text(encoding='utf-8-sig')
    if NEW_FIXTURE in old:
        print('ALREADY FIXED: supplier invoice test product has wholesale_price.', flush=True)
    elif old.count(OLD_FIXTURE) == 1:
        changes[supplier] = old.replace(OLD_FIXTURE, NEW_FIXTURE, 1)
    else:
        fail('Supplier test fixture does not match the expected Stage 13I version. No files changed.')

    old = INVENTORY.read_text(encoding='utf-8-sig')
    if NEW_STOCK_ASSERTION in old:
        print('ALREADY FIXED: inventory assertion checks the stock table cell.', flush=True)
    elif old.count(OLD_STOCK_ASSERTION) == 1:
        changes[INVENTORY] = old.replace(OLD_STOCK_ASSERTION, NEW_STOCK_ASSERTION, 1)
    else:
        fail('Inventory test assertion differs from the expected Stage 3 test. No files changed.')

    current_settings = SETTINGS.read_text(encoding='utf-8-sig')
    inactive = 'loyalty_ops.apps.LoyaltyOpsConfig' not in current_settings
    if LOYALTY.is_file():
        old = LOYALTY.read_text(encoding='utf-8-sig')
        if GUARD_MARKER in old:
            print('ALREADY FIXED: optional loyalty-test guard present.', flush=True)
        elif inactive:
            if not old.startswith('"""'):
                fail('Loyalty test header is unexpected; refusing automatic edit.')
            doc_end = old.find('"""', 3)
            if doc_end < 0:
                fail('Loyalty test docstring is malformed; refusing automatic edit.')
            cut = doc_end + 3
            changes[LOYALTY] = old[:cut] + '\n' + GUARD + old[cut:]
        else:
            print('INFO: Stage 13H is active, so its full tests remain enabled.', flush=True)
    elif inactive:
        print('INFO: loyalty_ops/tests.py absent; no optional-test guard required.', flush=True)

    for path, content in changes.items():
        ast.parse(content, filename=str(path))
    return changes


def main():
    print('SMARTMART ERP — STAGE 13I SUPPLIER AND TEST-SUITE REPAIR', flush=True)
    changes = updated_content()  # Refuse unexpected versions before any write.
    try:
        from smartmart_backup import create_backup, verify_backup
        backup = create_backup()
        verify_backup(backup)
    except Exception as exc:
        fail('Verified SQLite backup failed; no patches applied. ' + str(exc))
    print('VERIFIED PRIVATE BACKUP:', backup, flush=True)
    original_dir = backup / 'pre_stage13i_repair_files'
    try:
        for path, content in changes.items():
            rel = path.relative_to(ROOT)
            destination = original_dir / rel
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, destination)
            if sha(destination.read_bytes()) != sha(path.read_bytes()):
                raise RuntimeError('Original file backup verification failed for ' + str(rel))
        for path, content in changes.items():
            path.write_text(content, encoding='utf-8')
            print('PATCHED:', path.relative_to(ROOT), flush=True)
    except Exception as exc:
        for path in changes:
            saved = original_dir / path.relative_to(ROOT)
            if saved.is_file():
                shutil.copy2(saved, path)
        fail('Patching failed; original test files restored. ' + str(exc))

    print('RETRYING: python install_smartmart_stage13i.py', flush=True)
    try:
        result = subprocess.run([sys.executable, str(INSTALLER)], cwd=ROOT, check=False)
    except OSError as exc:
        fail('Could not start the Stage 13I installer: ' + str(exc))
    if result.returncode != 0:
        fail('Stage 13I installer returned ' + str(result.returncode)
             + '. It restores its configuration on failure. Test-file fixes remain for retry; '
             'the verified backup is ' + str(backup))

    print('\nRUNNING: python manage.py test --noinput', flush=True)
    result = subprocess.run([sys.executable, str(ROOT / 'manage.py'), 'test', '--noinput'],
                            cwd=ROOT, check=False)
    if result.returncode:
        fail('Stage 13I installer passed, but the full test suite still has failures. '
             'Share the new tracebacks; do not deploy or import prices yet. Backup: ' + str(backup))
    print('\nSTAGE 13I REPAIR COMPLETE: Full Django tests passed.', flush=True)
    print('Existing business data was not changed by this repair.')
    print('Supplier accounts: http://127.0.0.1:8002/supplier-accounts/')
    print('NEXT: python manage.py check', flush=True)


if __name__ == '__main__':
    main()
