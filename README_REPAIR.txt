SMARTMART ERP — STAGE 13A FIX (TEST-TOKEN LENGTH)

Problem:
Three new returns_ops tests produced checkout_token values of 67, 70,
and 71 characters. pos.services.complete_sale correctly refuses tokens
longer than 64 characters. The installer therefore stopped its tests.

This repair:
- Changes only returns_ops/tests.py by generating 40-character test tokens.
- Leaves checkout validation, sales, products, payments and stock unchanged.
- Makes a private copy of the old tests file (not the database).
- Reruns the original install_smartmart_stage13a.py, which makes its
  own verified private database backup before modifying Django config.
- Is safe to rerun; it will not add a duplicate fix.

DO THIS IN VS CODE POWERSHELL:

cd "C:\Users\USER\Documents\assignment\New folder\SmartMartERP"
Expand-Archive -LiteralPath "$env:USERPROFILE\Downloads\SmartMartERP_Stage13A_Test_Fix.zip" -DestinationPath . -Force
python repair_smartmart_stage13a.py

If successful, run:
python manage.py test --noinput
python manage.py check
python manage.py runserver 8002

If the installer reports another error, stop and share its full output.
Do not run migrate --fake, delete db.sqlite3, or run flush.
