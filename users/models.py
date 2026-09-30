# users/models.py
from django.contrib.auth.models import AbstractUser
from django.core.validators import RegexValidator
from django.db import models
from django.db.models import Q
from django.db.models.functions import Lower

phone_validator = RegexValidator(
    regex=r'^[6-9]\d{9}$',
    message='Enter a valid 10-digit Indian mobile number.',
)


class Role(models.TextChoices):
    CITIZEN = 'citizen', 'Citizen'
    CORPORATOR = 'corporator', 'Corporator'


class CustomUser(AbstractUser):
    phone = models.CharField(
        max_length=10,
        blank=True,
        validators=[phone_validator],
        help_text='10-digit mobile number.',
    )
    role = models.CharField(
        max_length=20,
        choices=Role.choices,
        default=Role.CITIZEN,
        db_index=True,
    )
    # Citizens: the ward they live in (unlocks the ward feed).
    # Corporators: the ward they answer for. A corporator with no ward is a
    # city-wide officer and can see every ward.
    ward = models.ForeignKey(
        'complaints.Ward',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='users',
    )
    notify_by_email = models.BooleanField(
        default=True,
        help_text='Email me when one of my complaints changes status or gets an official reply.',
    )
    # Notifications only go to addresses the user has proven they own.
    email_verified = models.BooleanField(default=False)

    class Meta:
        ordering = ['username']
        constraints = [
            # Case-insensitive uniqueness for non-blank emails, enforced by the
            # database so the forms, the API and the admin all obey it.
            models.UniqueConstraint(
                Lower('email'),
                condition=~Q(email=''),
                name='unique_user_email_ci',
                violation_error_message='An account with this email already exists.',
            ),
        ]

    def __str__(self):
        return f'{self.username} ({self.get_role_display()})'

    @property
    def is_corporator(self) -> bool:
        return self.role == Role.CORPORATOR

    @property
    def is_citizen(self) -> bool:
        return self.role == Role.CITIZEN

    @property
    def display_name(self) -> str:
        return self.get_full_name() or self.username

    @property
    def can_receive_email(self) -> bool:
        return bool(self.email and self.email_verified and self.notify_by_email)
