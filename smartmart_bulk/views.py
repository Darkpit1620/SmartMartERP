from decimal import Decimal
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.shortcuts import render
from django.views.decorators.http import require_GET

from core.models import Branch
from inventory.models import BranchStock, Category, Product
from inventory.permissions import allowed_store_profile


def department_icon(name):
    name = name.lower()
    for words, icon in [
        (("phone", "tablet", "mobile"), "📱"),
        (("computer", "office", "stationery"), "💻"),
        (("tv,", "audio", "camera"), "📺"),
        (("appliance", "electric", "lighting"), "🔌"),
        (("fruit",), "🍎"),
        (("vegetable",), "🥬"),
        (("rice", "grain", "pasta", "sugar"), "🌾"),
        (("beverage", "drinks", "water", "tea", "coffee"), "🥤"),
        (("meat", "fish", "seafood"), "🍗"),
        (("dairy", "bakery", "bread"), "🥛"),
        (("laundry", "cleaning", "paper", "hygiene"), "🧼"),
        (("beauty", "personal", "baby"), "🧴"),
        (("clothing", "footwear", "bags"), "👕"),
        (("furniture", "bedding", "textiles"), "🛋️"),
        (("hardware", "paint", "plumbing"), "🛠️"),
        (("sports", "fitness", "toys", "games"), "⚽"),
        (("automotive",), "🚗"),
        (("garden", "farming"), "🌱"),
        (("pet",), "🐾"),
    ]:
        if any(word in name for word in words):
            return icon
    return "🛒"


@login_required
@require_GET
def browse(request):
    profile = allowed_store_profile(request)  # Same role checks as existing product catalogue.
    branch_choices = Branch.objects.filter(active=True).order_by("name") if request.user.is_superuser else Branch.objects.none()
    if profile is None:
        branch_id = request.GET.get("branch", "")
        branch = branch_choices.filter(pk=int(branch_id)).first() if branch_id.isascii() and branch_id.isdigit() else branch_choices.first()
    else:
        branch = profile.branch if profile.branch_id else None

    departments = list(
        Category.objects.annotate(
            product_count=Count("products", filter=Q(products__is_active=True))
        ).filter(product_count__gt=0).order_by("name")
    )
    query = request.GET.get("q", "").strip()[:100]
    selected_category = request.GET.get("category", "").strip()
    in_stock_only = request.GET.get("stock", "") == "yes"

    products = Product.objects.select_related("category").filter(is_active=True)
    if query:
        products = products.filter(
            Q(name__icontains=query) | Q(sku__icontains=query) |
            Q(barcode__icontains=query) | Q(category__name__icontains=query)
        )
    if selected_category:
        if selected_category.isdigit():
            products = products.filter(category_id=int(selected_category))
        else:
            products = products.none()
    if in_stock_only:
        if branch:
            products = products.filter(
                pk__in=BranchStock.objects.filter(branch=branch, quantity__gt=0).values("product_id")
            )
        else:
            products = products.none()

    page = Paginator(products.order_by("name", "pk"), 36).get_page(request.GET.get("page"))
    product_ids = [p.pk for p in page.object_list]
    stocks = {
        x.product_id: x.quantity
        for x in BranchStock.objects.filter(branch=branch, product_id__in=product_ids)
    } if branch else {}
    cards = [
        {
            "product": product,
            "quantity": stocks.get(product.pk, Decimal("0")),
            "icon": department_icon(product.category.name),
        }
        for product in page.object_list
    ]
    available_in_branch = (
        BranchStock.objects.filter(
            branch=branch, quantity__gt=0, product__is_active=True
        ).count() if branch else 0
    )
    return render(request, "smartmart_bulk/catalogue.html", {
        "departments": departments,
        "popular_departments": sorted(departments, key=lambda d: -d.product_count)[:10],
        "selected_category": selected_category,
        "query": query,
        "in_stock_only": in_stock_only,
        "page": page,
        "cards": cards,
        "branch": branch,
        "branches": branch_choices,
        "branch_id": branch.pk if branch else "",
        "all_count": Product.objects.filter(is_active=True).count(),
        "department_count": len(departments),
        "available_in_branch": available_in_branch,
    })
