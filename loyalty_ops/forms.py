from django import forms
from core.models import Branch
from .models import LoyaltyReward


class MemberForm(forms.Form):
    branch = forms.ModelChoiceField(queryset=Branch.objects.filter(active=True))
    full_name = forms.CharField(max_length=140, min_length=2)
    phone = forms.CharField(max_length=35, required=False)
    consent = forms.BooleanField(label='Customer agreed to membership and linking purchase history')


class RewardForm(forms.ModelForm):
    class Meta:
        model = LoyaltyReward
        fields = ('branch', 'title', 'details', 'points_cost')


class ReceiptForm(forms.Form):
    receipt_number = forms.CharField(max_length=64, label='Existing POS receipt number (e.g. SM-2026-0000001)')
