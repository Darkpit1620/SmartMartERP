from decimal import Decimal
from django import forms
from django.utils import timezone
from trading.models import PurchaseOrder
from .models import SupplierPayment


class InvoiceForm(forms.Form):
    purchase_order = forms.ModelChoiceField(queryset=PurchaseOrder.objects.none(), label='Existing submitted purchase order')
    invoice_number = forms.CharField(max_length=80, label='Supplier invoice number')
    invoice_date = forms.DateField(widget=forms.DateInput(attrs={'type': 'date'}))
    due_date = forms.DateField(widget=forms.DateInput(attrs={'type': 'date'}))
    amount = forms.DecimalField(min_value=Decimal('0.01'), decimal_places=2, max_digits=14, label='Invoice total (KES)')
    note = forms.CharField(required=False, max_length=255, widget=forms.Textarea(attrs={'rows': 2}))

    def __init__(self, *args, branch=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['purchase_order'].queryset = PurchaseOrder.objects.filter(
            branch=branch, status__in=['ORDERED', 'PARTIAL', 'RECEIVED']).select_related('supplier') if branch else PurchaseOrder.objects.none()
        self.fields['invoice_date'].initial = timezone.localdate()
        self.fields['due_date'].initial = timezone.localdate()


class PaymentForm(forms.Form):
    amount = forms.DecimalField(min_value=Decimal('0.01'), decimal_places=2, max_digits=14, label='Amount actually paid (KES)')
    method = forms.ChoiceField(choices=SupplierPayment.Method.choices)
    reference = forms.CharField(max_length=100, label='Actual payment confirmation/reference')
    paid_on = forms.DateField(widget=forms.DateInput(attrs={'type': 'date'}), label='Payment date')
    note = forms.CharField(required=False, max_length=255, widget=forms.Textarea(attrs={'rows': 2}))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['paid_on'].initial = timezone.localdate()
