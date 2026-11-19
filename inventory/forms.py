from decimal import Decimal
from django import forms
from .models import Category, Product, StockMovement


INPUT_CLASS = "inventory-input"


class CategoryForm(forms.ModelForm):
    class Meta:
        model = Category
        fields = ["name", "description", "is_active"]
        widgets = {
            "name": forms.TextInput(attrs={"class": INPUT_CLASS, "placeholder": "e.g. Food & Groceries"}),
            "description": forms.TextInput(attrs={"class": INPUT_CLASS}),
        }


class ProductForm(forms.ModelForm):
    class Meta:
        model = Product
        fields = ["category", "name", "sku", "barcode", "unit", "cost_price", "retail_price",
                  "wholesale_price", "wholesale_min_qty", "reorder_level", "tax_rate", "is_active"]
        widgets = {
            "category": forms.Select(attrs={"class": INPUT_CLASS}),
            "name": forms.TextInput(attrs={"class": INPUT_CLASS, "placeholder": "e.g. Maize Flour 2 kg"}),
            "sku": forms.TextInput(attrs={"class": INPUT_CLASS, "placeholder": "e.g. FLOUR-2KG-001"}),
            "barcode": forms.TextInput(attrs={"class": INPUT_CLASS, "placeholder": "Scan or enter barcode (optional)"}),
            "unit": forms.Select(attrs={"class": INPUT_CLASS}),
            "cost_price": forms.NumberInput(attrs={"class": INPUT_CLASS, "step": "0.01", "min": "0"}),
            "retail_price": forms.NumberInput(attrs={"class": INPUT_CLASS, "step": "0.01", "min": "0"}),
            "wholesale_price": forms.NumberInput(attrs={"class": INPUT_CLASS, "step": "0.01", "min": "0"}),
            "wholesale_min_qty": forms.NumberInput(attrs={"class": INPUT_CLASS, "min": "1"}),
            "reorder_level": forms.NumberInput(attrs={"class": INPUT_CLASS, "min": "0", "step": "0.001"}),
            "tax_rate": forms.NumberInput(attrs={"class": INPUT_CLASS, "step": "0.01", "min": "0", "max": "100"}),
        }

    def clean_barcode(self):
        return (self.cleaned_data.get("barcode") or "").strip() or None

    def clean_sku(self):
        value = (self.cleaned_data.get("sku") or "").strip().upper()
        if Product.objects.filter(sku__iexact=value).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError("A product with this SKU already exists.")
        return value

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["category"].queryset = Category.objects.filter(is_active=True) | Category.objects.filter(pk=self.instance.category_id) if self.instance.pk else Category.objects.filter(is_active=True)


class StockMovementForm(forms.Form):
    kind = forms.ChoiceField(choices=[(value, label) for value, label in StockMovement.Kind.choices if value in ('RECEIPT', 'CORRECTION_IN', 'CORRECTION_OUT')], widget=forms.Select(attrs={"class": INPUT_CLASS}))
    quantity = forms.DecimalField(max_digits=12, decimal_places=3, min_value=Decimal("0.001"),
        widget=forms.NumberInput(attrs={"class": INPUT_CLASS, "min": "0.001", "step": "0.001"}))
    reference = forms.CharField(max_length=120, widget=forms.TextInput(attrs={"class": INPUT_CLASS, "placeholder": "Delivery note / stock count reference"}))
    note = forms.CharField(required=False, widget=forms.Textarea(attrs={"class": INPUT_CLASS, "rows": 3, "placeholder": "Optional explanation"}))
