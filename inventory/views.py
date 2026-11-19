from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_http_methods

from core.models import Branch
from .forms import CategoryForm, ProductForm, StockMovementForm
from .models import BranchStock, Product, StockMovement
from .permissions import allowed_store_profile, require_stock_staff
from .services import record_stock_movement


def _chosen_branch(request, profile):
    if profile is not None:
        if not profile.branch_id:
            raise PermissionDenied("Your account must have an assigned branch.")
        return profile.branch
    branches = Branch.objects.filter(active=True).order_by("name")
    requested = request.GET.get("branch")
    if requested:
        branch = branches.filter(pk=int(requested)).first() if requested.isascii() and requested.isdigit() else None
        if not branch:
            raise Http404("Branch not found or inactive.")
        return branch
    return branches.first()


@login_required
@require_http_methods(["GET"])
def product_list(request):
    allowed_store_profile(request)
    query = request.GET.get("q", "").strip()[:100]
    items = Product.objects.select_related("category")
    if query:
        items = items.filter(Q(name__icontains=query) | Q(sku__icontains=query) | Q(barcode__icontains=query))
    if not request.user.is_superuser:
        items = items.filter(is_active=True)
    pager = Paginator(items, 25)
    return render(request, "inventory/products.html", {
        "items": pager.get_page(request.GET.get("page")), "query": query,
        "can_manage": request.user.is_superuser,
    })


@login_required
@require_http_methods(["GET"])
def product_detail(request, pk):
    profile = allowed_store_profile(request)
    product = get_object_or_404(Product.objects.select_related("category"), pk=pk)
    if not product.is_active and not request.user.is_superuser:
        raise Http404("Product unavailable.")
    can_view_stock = request.user.is_superuser or (profile is not None and profile.role in ("MANAGER", "WAREHOUSE"))
    available = BranchStock.objects.filter(product=product).select_related("branch") if can_view_stock else BranchStock.objects.none()
    if profile is not None:
        available = available.filter(branch=profile.branch) if profile.branch_id else available.none()
    return render(request, "inventory/product_detail.html", {
        "product": product, "balances": available, "can_view_stock": can_view_stock,
        "show_cost": request.user.is_superuser or (profile is not None and profile.role == "MANAGER"),
    })


@login_required
@require_http_methods(["GET", "POST"])
def product_create(request):
    allowed_store_profile(request)
    if not request.user.is_superuser:
        raise PermissionDenied("Only administrators may create products.")
    form = ProductForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        product = form.save()
        messages.success(request, f"Product {product.sku} created. Its starting stock is zero in every branch.")
        return redirect("inventory:product_detail", pk=product.pk)
    return render(request, "inventory/edit_form.html", {
        "form": form, "heading": "Add supermarket product", "subheading": "Enter retail and wholesale prices and an optional barcode.",
        "button_text": "Save product", "back_url": reverse("inventory:product_list"),
    })


@login_required
@require_http_methods(["GET", "POST"])
def product_edit(request, pk):
    allowed_store_profile(request)
    if not request.user.is_superuser:
        raise PermissionDenied("Only administrators may edit products.")
    product = get_object_or_404(Product, pk=pk)
    form = ProductForm(request.POST or None, instance=product)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Product details updated. Stock balances were not changed.")
        return redirect("inventory:product_detail", pk=product.pk)
    return render(request, "inventory/edit_form.html", {
        "form": form, "heading": "Edit product", "subheading": product.name,
        "button_text": "Save changes", "back_url": reverse("inventory:product_detail", args=[pk]),
    })


@login_required
@require_http_methods(["GET", "POST"])
def category_create(request):
    allowed_store_profile(request)
    if not request.user.is_superuser:
        raise PermissionDenied("Only administrators may create categories.")
    form = CategoryForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Category created. You can now add products to it.")
        return redirect("inventory:product_create")
    return render(request, "inventory/edit_form.html", {
        "form": form, "heading": "Add product category", "subheading": "Organise products into departments and aisles.",
        "button_text": "Save category", "back_url": reverse("inventory:product_list"),
    })


@login_required
@require_http_methods(["GET"])
def stock_list(request):
    profile = require_stock_staff(request)
    branch = _chosen_branch(request, profile)
    branches = Branch.objects.filter(active=True).order_by("name") if request.user.is_superuser else []
    query = request.GET.get("q", "").strip()[:100]
    products = Product.objects.filter(is_active=True).select_related("category")
    if query:
        products = products.filter(Q(name__icontains=query) | Q(sku__icontains=query) | Q(barcode__icontains=query))
    page = Paginator(products, 30).get_page(request.GET.get("page"))
    stock_by_product = {
        stock.product_id: stock.quantity
        for stock in BranchStock.objects.filter(branch=branch, product_id__in=[p.id for p in page.object_list])
    } if branch else {}
    rows, low_count, stock_units = [], 0, 0
    for product in page:
        quantity = stock_by_product.get(product.pk, 0)
        is_low = quantity <= product.reorder_level
        low_count += int(is_low)
        stock_units += quantity
        rows.append({"product": product, "quantity": quantity, "low": is_low})
    total_products = Product.objects.filter(is_active=True).count()
    movement_count = StockMovement.objects.filter(branch=branch).count() if branch else 0
    return render(request, "inventory/stock.html", {
        "branch": branch, "branches": branches, "rows": rows, "page": page,
        "query": query, "low_on_page": low_count, "units_on_page": stock_units,
        "total_products": total_products, "movement_count": movement_count,
    })


@login_required
@require_http_methods(["GET", "POST"])
def stock_change(request, pk):
    profile = require_stock_staff(request)
    branch = _chosen_branch(request, profile)
    if branch is None:
        messages.error(request, "Create an active branch before recording stock.")
        return redirect("inventory:stock_list")
    product = get_object_or_404(Product, pk=pk, is_active=True)
    stock = BranchStock.objects.filter(branch=branch, product=product).first()
    form = StockMovementForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            record_stock_movement(
                branch=branch, product=product, actor=request.user,
                kind=form.cleaned_data["kind"], quantity=form.cleaned_data["quantity"],
                reference=form.cleaned_data["reference"], note=form.cleaned_data["note"],
            )
        except ValidationError as exc:
            form.add_error(None, exc)
        else:
            messages.success(request, f"Stock movement saved for {product.sku} at {branch.name}.")
            return redirect(f"{reverse('inventory:stock_list')}?branch={branch.pk}")
    return render(request, "inventory/stock_change.html", {
        "form": form, "product": product, "branch": branch,
        "on_hand": stock.quantity if stock else 0,
    })


@login_required
@require_http_methods(["GET"])
def movements(request):
    profile = require_stock_staff(request)
    branch = _chosen_branch(request, profile)
    records = StockMovement.objects.filter(branch=branch).select_related("product", "recorded_by") if branch else StockMovement.objects.none()
    page = Paginator(records, 30).get_page(request.GET.get("page"))
    return render(request, "inventory/movements.html", {"branch": branch, "page": page})
