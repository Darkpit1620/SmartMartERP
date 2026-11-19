from django import forms
from django.utils import timezone
from core.models import Branch
from .models import Expense


class ExpenseForm(forms.ModelForm):
    class Meta:
        model = Expense
        fields = ('branch', 'category', 'amount', 'incurred_on', 'reference', 'description')
        widgets = {
            'incurred_on': forms.DateInput(attrs={'type': 'date'}),
            'amount': forms.NumberInput(attrs={'min': '0.01', 'step': '0.01'}),
            'description': forms.TextInput(attrs={'placeholder': 'Explain the expense'}),
            'reference': forms.TextInput(attrs={'placeholder': 'Invoice / voucher number (optional)'}),
        }

    def __init__(self, *args, fixed_branch=None, **kwargs):
        super().__init__(*args, **kwargs)
        if fixed_branch is not None:
            self.fields.pop('branch')
        else:
            self.fields['branch'].queryset = Branch.objects.filter(active=True)
        self.fields['incurred_on'].initial = timezone.localdate()

    def clean_amount(self):
        amount = self.cleaned_data['amount']
        if amount <= 0:
            raise forms.ValidationError('Enter a positive expense amount.')
        return amount
