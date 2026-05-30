# users/forms.py
from django.contrib.auth.forms import UserCreationForm
from .models import CustomUser

class SignupForm(UserCreationForm):
    class Meta:
        model  = CustomUser
        fields = ['username', 'phone', 'password1', 'password2']