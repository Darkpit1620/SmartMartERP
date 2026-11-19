from django import forms
from django.contrib.auth.forms import AuthenticationForm
from django.core.exceptions import ValidationError
from .models import StaffProfile


class StoreLoginForm(AuthenticationForm):
    username = forms.CharField(
        label="Username",
        widget=forms.TextInput(attrs={
            "placeholder": "Enter your username",
            "autocomplete": "username",
            "autofocus": True,
        }),
    )
    password = forms.CharField(
        label="Password",
        strip=False,
        widget=forms.PasswordInput(attrs={
            "placeholder": "Enter your password",
            "autocomplete": "current-password",
        }),
    )

    def confirm_login_allowed(self, user):
        super().confirm_login_allowed(user)
        if user.is_superuser:
            return
        try:
            profile = user.store_profile
        except StaffProfile.DoesNotExist:
            profile = None
        if profile is None or not profile.is_approved:
            raise ValidationError(
                "This account is not approved for store access. Contact your manager.",
                code="not_approved",
            )
