SMARTMART ERP — STAGE 13D CSV REPORT FIX
========================================
Fixes the mismatch where the CSV exports KES 100 instead of KES 100.00.

1. Stop runserver if running (Ctrl+C).
2. Open your existing SmartMartERP folder in VS Code PowerShell.
3. Extract the ZIP into that SAME folder:
   Expand-Archive -LiteralPath "$env:USERPROFILE\Downloads\SmartMartERP_Stage13D_CSV_Fix.zip" -DestinationPath . -Force
4. Run:
   python repair_smartmart_stage13d.py
5. If the installer reports success, verify the full suite:
   python manage.py test --noinput
   python manage.py check
6. Start:
   python manage.py runserver 8002
   Browse to http://127.0.0.1:8002/insights/

The repair adjusts only the Stage 13D CSV export of monetary values; counts and
stock quantities are left unchanged. The original Stage 13D installer creates
its own verified private SQLite backup, applies configuration changes, and
runs Django tests. This repair also keeps a copy of the previous view file
outside your repository. On installer failure, the repair rolls back the view.

No product, sale, stock, return, expense, or employee row is changed intentionally.
The full Django tests must run on your Windows SmartMart environment.
