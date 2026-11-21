"""Safe, repeatable CSV formatting repair for SmartMart ERP Stage 13D.

Fixes display precision in the report CSV only, then reruns the original
Stage 13D installer. The installer creates its own verified private database
backup, performs Django checks and tests, and restores configuration on error.
"""
from datetime import datetime
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
VIEW = ROOT / 'reporting_insights' / 'views.py'
INSTALLER = ROOT / 'install_smartmart_stage13d.py'
MARKER = 'def _csv_money(value):'

MONEY_FIELDS = (
    'confirmed_sales',
    'unverified_sales',
    'included_tax',
    'retail_sales',
    'wholesale_sales',
    'paid_refunds',
    'approved_expenses',
    'pending_expenses',
    'estimated_cost',
    'inventory_value',
)


def stop(message):
    raise SystemExit('STAGE 13D REPAIR STOPPED: ' + message)


def repaired_source(source):
    """Patch only the expected Stage 13D CSV value formatting expressions."""
    if MARKER in source:
        # A repeat run should verify the complete patch, not silently assume it.
        expected = [f"_csv_money(report['{key}'])" for key in MONEY_FIELDS]
        expected += ["_csv_money(report['estimated_merchandise_margin'])",
                     "_csv_money(item['gross'])"]
        missing = [item for item in expected if item not in source]
        if missing:
            stop('Existing CSV formatter is incomplete; no changes made: ' + ', '.join(missing))
        return source, False

    if 'import csv\n' not in source:
        stop('Unrecognized CSV report source; no changes made.')
    for field in MONEY_FIELDS:
        old = f"report['{field}']"
        # money fields should occur once in the existing CSV view source
        if source.count(old) != 1:
            stop(f'Unexpected reference count for {field}; no changes made.')

    before = "    writer.writerow(['Confirmed sales (tax included)', report['confirmed_sales']])"
    if before not in source:
        stop('Expected Stage 13D CSV export was not detected; no changes made.')

    patched = source.replace('import csv\n', 'import csv\nfrom decimal import Decimal\n', 1)
    anchor = '\n\ndef permitted_filters(request):'
    helper = ('\n\ndef _csv_money(value):\n'
              '    """Export KES monetary values with exactly two decimal places."""\n'
              "    return format(Decimal(str(value)), '.2f')\n")
    if patched.count(anchor) != 1:
        stop('Could not safely locate report function boundary; no changes made.')
    patched = patched.replace(anchor, helper + anchor, 1)

    for field in MONEY_FIELDS:
        old = f"report['{field}']"
        patched = patched.replace(old, f'_csv_money({old})', 1)
    # The unavailable-margin label stays unchanged.
    old = "report['estimated_merchandise_margin'] if report['estimated_merchandise_margin'] is not None else 'Unavailable: missing cost data'"
    new = "_csv_money(report['estimated_merchandise_margin']) if report['estimated_merchandise_margin'] is not None else 'Unavailable: missing cost data'"
    if patched.count(old) != 1:
        stop('Margin display expression differs from expected; no changes made.')
    patched = patched.replace(old, new, 1)

    old = "item['qty'], item['gross']])"
    if patched.count(old) != 1:
        stop('Top-products CSV expression differs from expected; no changes made.')
    patched = patched.replace(old, "item['qty'], _csv_money(item['gross'])])", 1)
    compile(patched, str(VIEW), 'exec')
    return patched, True


def main():
    print('SMARTMART ERP STAGE 13D — CSV MONEY FORMATTING REPAIR', flush=True)
    for required in (ROOT / 'manage.py', VIEW, INSTALLER, ROOT / 'smartmart_backup.py'):
        if not required.is_file():
            stop(f'Missing {required.relative_to(ROOT)}. Extract the original Stage 13D package first.')

    source = VIEW.read_text(encoding='utf-8-sig')
    fixed, changed = repaired_source(source)
    backup_path = None
    if changed:
        # Keep a source-level rollback copy outside the Git repository.
        private_base = Path.home() / 'Documents' / 'SmartMartERP_Backups'
        backup_dir = private_base / ('Stage13D_CSV_Repair_' + datetime.now().strftime('%Y%m%d_%H%M%S_%f'))
        backup_dir.mkdir(parents=True, exist_ok=False)
        backup_path = backup_dir / 'views_before_repair.py'
        backup_path.write_text(source, encoding='utf-8')
        VIEW.write_text(fixed, encoding='utf-8')
        print('PATCH APPLIED: CSV money amounts will use exactly two decimal places.', flush=True)
        print('Private source backup:', backup_path, flush=True)
    else:
        print('ALREADY PATCHED: CSV monetary formatting already verified.', flush=True)

    print('RETRYING: original Stage 13D installer and its Django tests...', flush=True)
    command = [sys.executable, str(INSTALLER)]
    try:
        result = subprocess.run(command, cwd=ROOT, check=False)
    except OSError as exc:
        if changed:
            VIEW.write_text(source, encoding='utf-8')
        stop('Could not start installer; source file restored. ' + str(exc))
    if result.returncode != 0:
        if changed:
            VIEW.write_text(source, encoding='utf-8')
            print('CSV source rolled back because installation did not succeed.', flush=True)
        stop('Installer/tests failed. Existing business records were not intentionally changed. '
             'Review the installer output; do NOT delete your database.')

    print('\nSTAGE 13D REPAIR AND INSTALLATION COMPLETE.', flush=True)
    print('NEXT: python manage.py test --noinput', flush=True)
    print('NEXT: python manage.py check', flush=True)
    print('Open http://127.0.0.1:8002/insights/ as an approved manager or administrator.', flush=True)


if __name__ == '__main__':
    main()
