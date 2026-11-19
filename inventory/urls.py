from django.urls import path
from . import views

app_name = "inventory"

urlpatterns = [
    path("products/", views.product_list, name="product_list"),
    path("products/new/", views.product_create, name="product_create"),
    path("categories/new/", views.category_create, name="category_create"),
    path("products/<int:pk>/", views.product_detail, name="product_detail"),
    path("products/<int:pk>/edit/", views.product_edit, name="product_edit"),
    path("stock/", views.stock_list, name="stock_list"),
    path("stock/<int:pk>/change/", views.stock_change, name="stock_change"),
    path("movements/", views.movements, name="movements"),
]
