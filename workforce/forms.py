from django import forms
from .models import LeaveRequest


class LeaveRequestForm(forms.ModelForm):
    class Meta:
        model = LeaveRequest
        fields = ('leave_type', 'starts_on', 'ends_on', 'reason')
        widgets = {
            'starts_on': forms.DateInput(attrs={'type': 'date'}),
            'ends_on': forms.DateInput(attrs={'type': 'date'}),
            'reason': forms.Textarea(attrs={'rows': 3, 'placeholder': 'Optional explanation'}),
        }

    def clean(self):
        values = super().clean()
        start, end = values.get('starts_on'), values.get('ends_on')
        if start and end and end < start:
            self.add_error('ends_on', 'End date must not be earlier than start date.')
        return values
