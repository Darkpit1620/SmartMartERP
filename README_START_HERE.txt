SMARTMART ERP STAGE 11D — STAGING VERIFICATION & LAUNCH SAFETY
=============================================================

IMPORTANT
  Stage 11D verifies a deployment; it does not create one.
  Do NOT assume your Render site is online until Render shows Live.
  This package does not modify local database, stock, settings, staff, or sales.

WINDOWS INSTALL
  1. Download ZIP to Downloads.
  2. Open VS Code terminal in SmartMartERP project root.
  3. Stop runserver if desired (not required).
  4. Run:
     Expand-Archive -LiteralPath "$env:USERPROFILE\Downloads\SmartMartERP_Stage11D_Staging_Verification.zip" -DestinationPath . -Force
     python install_smartmart_stage11d.py
     python smartmart_stage11d_verify.py --mode local

  Optional thorough test suite (creates and destroys ONLY Django temporary test DB):
     python smartmart_stage11d_verify.py --mode local --full-tests

  Once the Stage 11B Render site is LIVE, run from your Windows terminal:
     python smartmart_stage11d_verify.py --mode remote --url https://YOUR-ACTUAL-SERVICE.onrender.com

  Then run in your Render web-service SHELL, from the deployed project folder:
     python smartmart_stage11d_verify.py --mode server

  Note: Render needs the Stage11D script in the GitHub repository to use it in Shell.
  Git review:
     git add smartmart_stage11d_verify.py
     git diff --cached --name-only
     git commit -m "Add read-only SmartMart staging verification"
     git push origin main

  Never put DATABASE_URL, API tokens, passwords, or real customer data into chat.
  The complete review checklist is in stage11d_verification/README.md.

EXIT STATUS
  0: automated checks passed; manual review items may remain.
  2: one or more checks failed; do not treat staging as launch-ready.

No production launch authorization, payments, or tax-compliance certification
is provided by these checks.
