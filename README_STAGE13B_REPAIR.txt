SMARTMART ERP - STAGE 13B CASHIER SHIFT TEST FIX
================================================

WHY THE INSTALLER STOPPED
The cash drawer service correctly reloads and updates the shift in the database.
One test asserted against an older, stale Python model instance instead of
refreshing the saved record first. The installer automatically rolled back its
Django settings changes, so a full test run then could not import shift_ops.

THIS FIX
- Changes exactly one test assertion, adding sh.refresh_from_db().
- Does not change cashier shifts, the POS checkout service, models, migrations,
  existing supermarket data, or database tables.
- Saves the original test file to your private Documents/SmartMartERP_Backups.
- Reruns the original Stage 13B installer, which makes a verified database
  backup and runs the Stage 13A and Stage 13B tests.
- Is safe to run again; it will not duplicate the fix.

INSTRUCTIONS (VS Code PowerShell)
1. Open SmartMartERP and make sure your virtual environment is active.
2. Extract SmartMartERP_Stage13B_Test_Fix.zip in the SmartMartERP root:
   Expand-Archive -LiteralPath "$env:USERPROFILE\Downloads\SmartMartERP_Stage13B_Test_Fix.zip" -DestinationPath . -Force
3. Run:
   python repair_smartmart_stage13b.py
4. If the installation passes, run:
   python manage.py test --noinput
   python manage.py check
   python manage.py runserver 8002
5. Open http://127.0.0.1:8002/shifts/ as an approved cashier or manager.

IMPORTANT
Do not run the full test suite before the installer succeeds. If the installer
has rolled back Django settings, shift_ops/tests.py remains on disk but the
shift_ops app is not in INSTALLED_APPS, causing a test-import error.

No live payments or cash payouts are processed by this package. It is a local
development repair. The complete Django tests must run on your own computer.
