"""SmartMart ERP: propose wholesale prices from the ACTUAL live retail prices.

READ-ONLY: writes two local CSV files; never updates a database row.

Run in the SmartMartERP root with the project's Python virtualenv activated:
  python smartmart_prepare_wholesale_from_live.py
  python smartmart_prepare_wholesale_from_live.py --discount 5

After independent price/cost approval, import the CSV on the existing /pricing/
admin page using Preview followed by Import.  This is a discount-based policy,
NOT verified Kenyan wholesale-market pricing.
"""

import argparse
import csv
from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import os
from pathlib import Path
import sys

BASE = Path(__file__).resolve().parent
SOURCE = BASE / 'smartmart_bulk' / 'data' / 'smartmart_bulk_catalogue.csv'
MONEY = Decimal('0.01')


def stop(message):
    raise SystemExit('STOPPED SAFELY: ' + str(message) + '\nYour database was not modified.')


def main():
    parser = argparse.ArgumentParser(description='Prepare review-only wholesale prices from LIVE SmartMart retail prices (no database changes).')
    parser.add_argument('--discount', default='5', help='Wholesale discount percentage; default 5 (allowed: 1 to 20).')
    args = parser.parse_args()
    try:
        discount = Decimal(args.discount)
    except (InvalidOperation, ValueError):
        stop('Enter an ordinary discount percentage between 1 and 20, e.g. --discount 5.')
    if not discount.is_finite() or discount < Decimal('1') or discount > Decimal('20'):
        stop('Discount must be 1 to 20 percent. Larger discounts need a separately reviewed policy.')
    if not (BASE / 'manage.py').is_file() or not SOURCE.is_file():
        stop('Run this script from the existing SmartMartERP root. Required manage.py or original catalogue is missing.')
    with SOURCE.open('r', encoding='utf-8-sig', newline='') as fp:
        reader = csv.DictReader(fp)
        skus = []
        for line, row in enumerate(reader, 2):
            sku = (row.get('sku') or '').strip().upper()
            if not sku or sku in skus:
                stop(f'Missing or duplicate SKU in original catalogue at line {line}.')
            skus.append(sku)
    if len(skus) != 4926:
        stop(f'Expected original bulk catalogue to have exactly 4,926 SKUs, found {len(skus)}. Contact developer for review.')
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
    try:
        import django
        django.setup()
        from inventory.models import Product
    except Exception as exc:
        stop(f'Could not read existing Django catalogue: {exc}')
    existing = {obj['sku']: obj for obj in Product.objects.filter(sku__in=skus).values(
        'sku', 'name', 'retail_price', 'wholesale_price', 'cost_price', 'wholesale_min_qty'
    )}
    missing = [sku for sku in skus if sku not in existing]
    if missing:
        stop(f'{len(missing)} catalogue SKUs not present in live database (e.g. {", ".join(missing[:5])}). Do not import stale prices.')
    proposals, reviews = [], []
    skipped_populated = []
    blocked_cost = []
    blocked_retail = []
    discount_fraction = discount / Decimal('100')
    for sku in skus:
        p = existing[sku]
        retail = p['retail_price']
        current_wholesale = p['wholesale_price']
        cost = p['cost_price']
        if retail is None or retail <= 0:
            blocked_retail.append(sku)
            continue
        proposed = (retail * (Decimal('1') - discount_fraction)).quantize(MONEY, rounding=ROUND_HALF_UP)
        if proposed <= 0 or proposed >= retail:
            blocked_retail.append(sku)
            continue
        if current_wholesale is not None and current_wholesale > 0:
            skipped_populated.append(sku)
            continue  # Never overwrite an existing wholesale price automatically.
        if cost is not None and cost > 0 and proposed <= cost:
            blocked_cost.append(sku)
            continue  # Do not knowingly propose a zero/negative gross-margin price.
        proposals.append((sku, f'{proposed:.2f}'))
        reviews.append((sku, p['name'], f'{retail:.2f}', f'{discount}%', f'{proposed:.2f}',
                        f'{cost:.2f}' if cost else '', str(p['wholesale_min_qty']),
                        'CHECK SUPPLIER COST / MARGIN BEFORE APPROVAL'))
    if blocked_retail:
        stop(f'{len(blocked_retail)} bulk catalogue products lack usable retail prices (first: {blocked_retail[:5]}). No import files generated.')
    if blocked_cost:
        stop(f'{len(blocked_cost)} prices would be at/below existing supplier cost (first: {blocked_cost[:5]}). No import files generated. Review margins and costs first.')
    if not proposals:
        stop(f'No wholesale prices need filling. {len(skipped_populated)} target products already have a wholesale price.')
    # Avoid overwriting a CSV that the owner has already reviewed and edited.
    stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    name = str(discount).replace('.', 'p')
    import_path = BASE / f'SmartMart_Live_Wholesale_Import_{name}pct_{stamp}.csv'
    review_path = BASE / f'SmartMart_Live_Wholesale_Review_{name}pct_{stamp}.csv'
    if import_path.exists() or review_path.exists():
        stop('Proposed output files already exist; rerun after a second to avoid overwriting any manual review.')
    with import_path.open('w', encoding='utf-8-sig', newline='') as fh:
        writer = csv.writer(fh)
        writer.writerow(('sku', 'wholesale_price'))
        writer.writerows(proposals)
    with review_path.open('w', encoding='utf-8-sig', newline='') as fh:
        writer = csv.writer(fh)
        writer.writerow(('sku', 'product_name', 'live_retail_price_kes', 'wholesale_discount_policy',
                         'proposed_wholesale_price_kes', 'recorded_cost_price_if_any',
                         'existing_wholesale_min_qty', 'approval_note'))
        for row in reviews:
            # Avoid CSV formula injection when someone opens a product name in Excel.
            safe_row = list(row)
            for idx in (0, 1, 7):
                value = str(safe_row[idx])
                if value.lstrip().startswith(('=', '+', '-', '@')):
                    safe_row[idx] = "'" + value
            writer.writerow(safe_row)
    print('\nSMARTMART ERP — WHOLESALE PRICING PROPOSAL (READ ONLY)')
    print(f'Original bulk catalogue SKUs: {len(skus):,}')
    print(f'Proposed new wholesale prices: {len(proposals):,}')
    print(f'Already priced; skipped to preserve values: {len(skipped_populated):,}')
    print(f'Provisional discount from ACTUAL live retail: {discount}%')
    print(f'Existing quantity thresholds: UNCHANGED')
    print('Supplier cost prices: UNCHANGED / not inferred')
    print('Existing stock/sales/retail prices: UNCHANGED')
    print('Database rows changed by this script: ZERO')
    print('\nFirst three wholesale suggestions:')
    for sku, price in proposals[:3]:
        print(f'  {sku} -> KES {price}')
    print('\nReview file:  ', review_path)
    print('Import file:  ', import_path)
    print('\nNEXT: Verify wholesale pricing against supplier costs, create a database backup,')
    print('then open http://127.0.0.1:8002/pricing/ as superuser, CHECK / PREVIEW,')
    print('and ONLY THEN import the approved CSV. Never import the review CSV.')


if __name__ == '__main__':
    main()
