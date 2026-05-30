# users/models.py
from django.contrib.auth.models import AbstractUser
from django.db import models

class CustomUser(AbstractUser):
    ROLES = [
        ('citizen',     'Citizen'),
        ('corporator',  'Corporator'),
    ]
    phone = models.CharField(max_length=15, blank=True)
    role  = models.CharField(max_length=20, choices=ROLES, default='citizen')

    def __str__(self):
        return f"{self.username} ({self.role})"