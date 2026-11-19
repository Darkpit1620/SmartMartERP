from django import forms
from django.contrib.auth import get_user_model, password_validation
from django.core.exceptions import ValidationError

from core.models import Branch, StaffProfile


class EmployeeCreateForm(forms.Form):
    username = forms.CharField(max_length=150, help_text="Employee username for SmartMart login")
    first_name = forms.CharField(max_length=150)
    last_name = forms.CharField(max_length=150)
    email = forms.EmailField()
    role = forms.ChoiceField(choices=StaffProfile.Role.choices)
    branch = forms.ModelChoiceField(queryset=Branch.objects.none(), empty_label="Choose a branch")
    password1 = forms.CharField(label="Initial password", strip=False, widget=forms.PasswordInput(
        attrs={"autocomplete": "new-password", "class": "sm-password"}
    ))
    password2 = forms.CharField(label="Confirm password", strip=False, widget=forms.PasswordInput(
        attrs={"autocomplete": "new-password", "class": "sm-password"}
    ))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["branch"].queryset = Branch.objects.filter(active=True).order_by("name")
        for field in self.fields.values():
            field.widget.attrs.setdefault("class", "sm-input")

    def clean_username(self):
        value = self.cleaned_data["username"].strip()
        if get_user_model()._default_manager.filter(username__iexact=value).exists():
            raise ValidationError("This username is already taken.")
        username_field = get_user_model()._meta.get_field(get_user_model().USERNAME_FIELD)
        for validator in username_field.validators:
            validator(value)
        return value

    def clean_email(self):
        value = self.cleaned_data["email"].strip().lower()
        # A shared office email is not suitable for individual employee accounts.
        if get_user_model()._default_manager.filter(email__iexact=value).exists():
            raise ValidationError("This email is already assigned to an employee.")
        return value

    def clean(self):
        data = super().clean()
        p1, p2 = data.get("password1"), data.get("password2")
        if p1 and p2:
            if p1 != p2:
                self.add_error("password2", "The passwords do not match.")
            else:
                user = get_user_model()(
                    username=data.get("username", ""),
                    first_name=data.get("first_name", ""),
                    last_name=data.get("last_name", ""),
                    email=data.get("email", ""),
                )
                try:
                    password_validation.validate_password(p1, user)
                except ValidationError as exc:
                    self.add_error("password1", exc)
        return data


class BranchCreateForm(forms.ModelForm):
    class Meta:
        model = Branch
        fields = ("name", "code", "address", "phone", "active")
        widgets = {
            "name": forms.TextInput(attrs={"placeholder": "e.g. Mombasa Main Branch"}),
            "code": forms.TextInput(attrs={"placeholder": "e.g. MSA-MAIN"}),
        }

    def clean_code(self):
        return self.cleaned_data["code"].strip().upper()

    def clean_name(self):
        return self.cleaned_data["name"].strip()
