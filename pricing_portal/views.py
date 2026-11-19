import csv

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse
from django.shortcuts import render
from django.views.decorators.http import require_http_methods, require_GET

from inventory.models import Product
from .services import (
    EXPORT_FIELDS, PricingValidationError, commit_updates, plan_updates,
    read_csv, safe_excel_cell,
)


def _require_admin(request):
    # This is company-wide catalogue pricing, not a branch manager's setting.
    if not request.user.is_active or not request.user.is_superuser:
        raise PermissionDenied("Only head-office administrators may change company-wide prices.")


@login_required
@require_http_methods(["GET", "POST"])
def pricing_home(request):
    _require_admin(request)
    error = None
    preview = None
    imported_count = None
    action = None
    if request.method == "POST":
        action = request.POST.get("action", "preview")
        upload = request.FILES.get("csv_file")
        if not upload:
            error = "Choose a CSV file first."
        elif not upload.name.lower().endswith(".csv"):
            error = "Choose a .csv file. Spreadsheet (.xlsx) files must be saved as CSV UTF-8 first."
        elif action not in ("preview", "import"):
            error = "Invalid action. No prices were changed."
        else:
            try:
                records = read_csv(upload)
                preview = plan_updates(records)
                if action == "import":
                    imported_count = commit_updates(records)
            except PricingValidationError as exc:
                error = str(exc)
    return render(request, "pricing_portal/pricing.html", {
        "product_count": Product.objects.count(),
        "unpriced_retail": Product.objects.filter(is_active=True, retail_price__lte=0).count(),
        "unpriced_wholesale": Product.objects.filter(is_active=True, wholesale_price__lte=0).count(),
        "priced_retail": Product.objects.filter(is_active=True, retail_price__gt=0).count(),
        "error": error, "preview": preview, "imported_count": imported_count,
        "action": action,
    })


@login_required
@require_GET
def download_template(request):
    _require_admin(request)
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = 'attachment; filename="smartmart_verified_prices.csv"'
    response.write("\ufeff")  # Excel-compatible UTF-8 BOM
    writer = csv.writer(response)
    writer.writerow(EXPORT_FIELDS)
    products = Product.objects.select_related("category").order_by("sku")
    for p in products.iterator(chunk_size=500):
        writer.writerow([
            safe_excel_cell(p.sku), safe_excel_cell(p.name),
            safe_excel_cell(p.category.name),
            str(p.retail_price) if p.retail_price > 0 else "",
            str(p.wholesale_price) if p.wholesale_price > 0 else "",
            str(p.cost_price) if p.cost_price > 0 else "",
            str(p.wholesale_min_qty) if p.wholesale_min_qty != 6 else "",
            str(p.tax_rate) if p.tax_rate > 0 else "",
        ])
    return response
