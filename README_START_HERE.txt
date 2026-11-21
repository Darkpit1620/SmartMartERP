SMARTMART ERP — WHOLESALE PRICING NEXT STEP
21 November 2026

Your last reported operations audit:
- Products: 4,934
- Unpriced retail: 0
- Unpriced wholesale: 4,926
- Unstocked: 4,926

WHAT THIS PACKAGE DOES
Provides a PROVISIONAL wholesale selling-price policy: 5% below each
retail price, for wholesale quantities already configured on each product
(default six units for generic products). This is a business rule, NOT an
independently verified Kenyan wholesale or supplier-cost quotation.

Recommended safe workflow: calculate from your LIVE SmartMart prices.
1. Extract this ZIP into your existing SmartMartERP project directory.
2. In the activated .venv PowerShell, from the SmartMartERP root:
   python smartmart_prepare_wholesale_from_live.py
3. The script only reads the database. It creates two CSV files in the
   project root: SmartMart_Live_Wholesale_Import_...csv and
   SmartMart_Live_Wholesale_Review_...csv.
4. Review the second file and validate intended margin versus actual
   supplier acquisition costs. The script will refuse to propose wholesale
   prices below any positive supplier cost already stored.
5. Create verified backup: python smartmart_backup.py
6. Start local Django: python manage.py runserver 8002
7. Log in as the Django superuser at http://127.0.0.1:8002/pricing/
8. Select ONLY the ...Live_Wholesale_Import_...csv.
9. Click Check / Preview. Confirm count and intended changes.
10. Select the SAME CSV again if required and import approved wholesale prices.
11. Back in PowerShell, run: python manage.py smartmart_audit
    Expected unpriced wholesale: 0 if all 4,926 SKUs were still missing
    wholesale prices and the entire proposal was accepted.

ALTERNATIVE STATIC PROPOSAL
- SmartMart_Kenya_Wholesale_Proposal_4926.csv is precomputed at 5% below
  the EARLIER estimated retail file. It may be STALE if your live retail
  prices differ from those estimates. Prefer generating from live.
- SmartMart_Kenya_Wholesale_Review_4926.xlsx is a reference review file.
  Its formulas can be edited, but XLSX cannot be uploaded directly to /pricing/.

SCOPE AND SAFETY
- Only 4,926 original SmartMart bulk SKUs are selected; the eight starter
  training products remain untouched.
- Import CSV has only: sku,wholesale_price. It cannot change retail,
  supplier cost, taxes, wholesale thresholds, staff, sales or stock.
- Live proposal script makes ZERO database writes. It skips already-priced
  products and stops if positive supplier costs indicate below-cost pricing.
- Actual wholesale profit margins CANNOT be verified without supplier costs.
- A retail discount is NOT evidence of the Kenyan wholesale market rate.
- Never set fictitious stock or cost prices.

If any preview or test fails, stop. Do not reset db.sqlite3.
