from decimal import Decimal
from django import forms
from django.core.exceptions import ValidationError
from core.models import Branch
from .models import StockTransfer

FIELD_CLASS = 'transfer-input'


class StockTransferForm(forms.ModelForm):
    class Meta:
        model = StockTransfer
        fields = ('source_branch', 'destination_branch', 'notes')
        widgets = {
            'source_branch': forms.Select(attrs={'class': FIELD_CLASS}),
            'destination_branch': forms.Select(attrs={'class': FIELD_CLASS}),
            'notes': forms.Textarea(attrs={'class': FIELD_CLASS, 'rows': 3, 'placeholder': 'Optional reason for transfer'}),
        }

    def __init__(self, *args, assigned_branch=None, **kwargs):
        super().__init__(*args, **kwargs)
        active = Branch.objects.filter(active=True).order_by('name')
        self.fields['source_branch'].queryset = active
        self.fields['destination_branch'].queryset = active.exclude(pk=assigned_branch.pk) if assigned_branch else active
        if assigned_branch:
            self.fields.pop('source_branch')
        self.assigned_branch = assigned_branch

    def clean(self):
        cleaned = super().clean()
        source = self.assigned_branch or cleaned.get('source_branch')
        dest = cleaned.get('destination_branch')
        if source and dest and source.pk == dest.pk:
            raise ValidationError('Choose a destination different from the sending branch.')
        return cleaned


class TransferLineForm(forms.Form):
    product_code = forms.CharField(max_length=64, label='Product SKU or barcode',
                                   widget=forms.TextInput(attrs={'class': FIELD_CLASS, 'placeholder': 'Scan barcode or enter SKU'}))
    quantity = forms.DecimalField(max_digits=12, decimal_places=3, min_value=Decimal('0.001'),
                                  widget=forms.NumberInput(attrs={'class': FIELD_CLASS, 'min': '0.001', 'step': '0.001'}))
