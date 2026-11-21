"""
URL configuration for config project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('supplier-accounts/', include('supplier_accounts.urls')),
    path('labels/', include('label_printing.urls')),
    path('documents/', include('sales_documents.urls')),
    path('insights/', include('reporting_insights.urls')),
    path('alerts/', include('stock_alerts.urls')),
    path('shifts/', include('shift_ops.urls')),
    path('returns/', include('returns_ops.urls')),
    path("transaction-tests/", include("transaction_checks.urls")),
    path("employees/", include("staff_activation.urls")),
    path("pricing/", include("pricing_portal.urls")),
    path("operations/", include("operations.urls")),
    path("finance/", include("finance_ops.urls")),
    path("workforce/", include("workforce.urls")),
    path("transfers/", include("transfers.urls")),
    path("trade/", include("trading.urls")),
    path("pos/", include("pos.urls")),
    path("catalogue/", include("smartmart_bulk.urls")),
    path("inventory/", include("inventory.urls")),
    path("", include("core.urls")),
    path('admin/', admin.site.urls),
]
