from django.urls import path, reverse_lazy
from django.contrib.auth import views as auth_views
from . import views

app_name = "staff_activation"
urlpatterns = [
    path("", views.home, name="home"),
    path("create/", views.create_employee, name="create_employee"),
    path("branches/create/", views.create_branch, name="create_branch"),
    path("change-password/", auth_views.PasswordChangeView.as_view(
        template_name="staff_activation/form.html",
        success_url=reverse_lazy("staff_activation:password_changed"),
        extra_context={"heading": "Change my password", "summary": "Enter your current password and choose a new secure password.", "password_controls": True},
    ), name="change_password"),
    path("password-changed/", auth_views.PasswordChangeDoneView.as_view(
        template_name="staff_activation/password_changed.html",
    ), name="password_changed"),
    path("<int:pk>/review/", views.review_employee, name="review_employee"),
]
