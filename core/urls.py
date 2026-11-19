from django.contrib.auth import views as auth_views
from django.urls import path
from . import views
from .forms import StoreLoginForm

app_name = "core"

urlpatterns = [
    path("", views.home, name="home"),
    path("login/", auth_views.LoginView.as_view(
        template_name="core/login.html",
        authentication_form=StoreLoginForm,
        redirect_authenticated_user=True,
    ), name="login"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("dashboard/", views.dashboard, name="dashboard"),
    path("portal/admin/", views.admin_portal, name="admin_portal"),
    path("portal/manager/", views.manager_portal, name="manager_portal"),
    path("portal/cashier/", views.cashier_portal, name="cashier_portal"),
    path("portal/warehouse/", views.warehouse_portal, name="warehouse_portal"),
    path("portal/staff/", views.staff_portal, name="staff_portal"),
]
