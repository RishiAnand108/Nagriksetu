# complaints/signals.py
from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import Complaint
from core.utils import watermark_image

@receiver(post_save, sender=Complaint)
def stamp_photo_on_save(sender, instance, created, **kwargs):
    if created and instance.image:
        watermark_image(instance)