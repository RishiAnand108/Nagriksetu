# complaints/forms.py
from django import forms
from .models import Complaint

class ComplaintForm(forms.ModelForm):

    class Meta:
        model  = Complaint
        fields = ['issue_type', 'description', 'image']
        # latitude + longitude are NOT here
        # they will be filled by GPS JavaScript silently

        widgets = {
            'issue_type': forms.Select(attrs={
                'class': 'form-select'
            }),
            'description': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Describe the issue...'
            }),
            'image': forms.FileInput(attrs={
                'class': 'form-control',
                'accept': 'image/*;capture=camera'
                # capture=camera → opens camera directly on mobile
            }),
        }