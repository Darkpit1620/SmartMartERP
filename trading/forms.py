from decimal import Decimal
from django import forms
from .models import Supplier, WholesaleCustomer, PurchaseOrder, WholesaleOrder
from inventory.models import Product


class SupplierForm(forms.ModelForm):
    class Meta:
        model = Supplier
        fields = ['name', 'contact_person', 'phone', 'email', 'address']


class CustomerForm(forms.ModelForm):
    class Meta:
        model = WholesaleCustomer
        fields = ['name', 'business_name', 'phone', 'email', 'address']


class PurchaseOrderForm(forms.ModelForm):
    class Meta:
        model = PurchaseOrder
        fields = ['supplier', 'notes']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['supplier'].queryset = Supplier.objects.filter(is_active=True)


class WholesaleOrderForm(forms.ModelForm):
    class Meta:
        model = WholesaleOrder
        fields = ['customer', 'notes']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['customer'].queryset = WholesaleCustomer.objects.filter(is_active=True)


class PurchaseLineForm(forms.Form):
    product_code = forms.CharField(max_length=64, label='Product SKU or barcode')
    quantity = forms.DecimalField(min_value=Decimal('0.001'), max_digits=12, decimal_places=3)
    unit_cost = forms.DecimalField(min_value=Decimal('0.01'), max_digits=12, decimal_places=2,
                                   help_text='Supplier cost per selling unit (KES).')



class WholesaleLineForm(forms.Form):
    product_code = forms.CharField(max_length=64, label='Product SKU or barcode')
    quantity = forms.DecimalField(min_value=Decimal('0.001'), max_digits=12, decimal_places=3)

