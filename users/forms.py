# users/forms.py
from django import forms
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm

from users.models import Role

from . import services
from .models import CustomUser

FIELD_ATTRS = {'class': 'field-input'}


class SignupForm(UserCreationForm):
    email = forms.EmailField(
        required=False,
        help_text='Optional. Used only for updates on your complaints — we will ask you to confirm it.',
        widget=forms.EmailInput(attrs={**FIELD_ATTRS, 'placeholder': 'you@example.com', 'autocomplete': 'email'}),
    )

    class Meta:
        model = CustomUser
        fields = ['username', 'email', 'phone', 'ward']
        widgets = {
            'username': forms.TextInput(attrs={**FIELD_ATTRS, 'autofocus': True, 'autocomplete': 'username'}),
            'phone': forms.TextInput(attrs={**FIELD_ATTRS, 'placeholder': '10-digit mobile', 'inputmode': 'numeric',
                                            'autocomplete': 'tel-national'}),
            'ward': forms.Select(attrs=FIELD_ATTRS),
        }
        help_texts = {
            'ward': 'Your home ward. You will see (and can support) other reports from it.',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name in ('password1', 'password2'):
            self.fields[name].widget.attrs.update({**FIELD_ATTRS, 'autocomplete': 'new-password'})
        self.fields['ward'].required = False
        self.fields['ward'].empty_label = 'I am not sure'

    def clean_email(self):
        email = (self.cleaned_data.get('email') or '').strip()
        if services.email_in_use(email):
            raise forms.ValidationError('An account with this email already exists.')
        return email

    def save(self, commit=True):
        user = super().save(commit=False)
        # Role is never taken from the form — a citizen must not be able to
        # sign themselves up as a corporator. Staff assign that in the admin.
        user.role = Role.CITIZEN
        user.email_verified = False
        if commit:
            user.save()
        return user


class StyledAuthenticationForm(AuthenticationForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['username'].widget.attrs.update({**FIELD_ATTRS, 'autofocus': True, 'autocomplete': 'username'})
        self.fields['password'].widget.attrs.update({**FIELD_ATTRS, 'autocomplete': 'current-password'})


class ProfileForm(forms.ModelForm):
    class Meta:
        model = CustomUser
        fields = ['first_name', 'last_name', 'email', 'phone', 'ward', 'notify_by_email']
        widgets = {
            'first_name': forms.TextInput(attrs={**FIELD_ATTRS, 'autocomplete': 'given-name'}),
            'last_name': forms.TextInput(attrs={**FIELD_ATTRS, 'autocomplete': 'family-name'}),
            'email': forms.EmailInput(attrs={**FIELD_ATTRS, 'autocomplete': 'email'}),
            'phone': forms.TextInput(attrs={**FIELD_ATTRS, 'inputmode': 'numeric', 'autocomplete': 'tel-national'}),
            'ward': forms.Select(attrs=FIELD_ATTRS),
        }
        labels = {'notify_by_email': 'Email me about my complaints'}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['ward'].empty_label = 'Not set'
        if self.instance.is_corporator:
            # A corporator's ward is their jurisdiction, assigned by staff.
            self.fields['ward'].disabled = True
            self.fields['ward'].help_text = 'Your jurisdiction is assigned by the municipal administrator.'

    def clean_email(self):
        email = (self.cleaned_data.get('email') or '').strip()
        if services.email_in_use(email, exclude_pk=self.instance.pk):
            raise forms.ValidationError('Another account already uses this email.')
        return email

    def save(self, commit=True):
        # Route the email through the service so a change resets verification.
        new_email = self.cleaned_data.get('email', '')
        user = super().save(commit=False)
        user.email = CustomUser.objects.filter(pk=user.pk).values_list('email', flat=True).first() or ''
        self.email_changed = services.apply_email_change(user, new_email)
        if commit:
            user.save()
        return user
