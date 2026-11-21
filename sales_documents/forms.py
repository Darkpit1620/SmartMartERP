from django import forms
from .models import BranchPrintBrand, SaleCustomerDetails


class BranchBrandForm(forms.ModelForm):
    class Meta:
        model = BranchPrintBrand
        fields = ('trade_name', 'business_number', 'address', 'phone', 'email', 'footer')
        widgets = {'footer': forms.TextInput(attrs={'placeholder': 'Thank you for shopping with us'})}


class CustomerDetailsForm(forms.ModelForm):
    class Meta:
        model = SaleCustomerDetails
        fields = ('customer_name', 'customer_phone', 'customer_email',
                  'customer_address', 'customer_reference', 'note')

    def clean(self):
        cleaned = super().clean()
        any_other = any(cleaned.get(key) for key in (
            'customer_phone', 'customer_email', 'customer_address', 'customer_reference'))
        if any_other and not cleaned.get('customer_name'):
            self.add_error('customer_name', 'Enter a customer name when recording contact details.')
        return cleaned
