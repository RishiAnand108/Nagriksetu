# complaints/signals.py
"""
Signal handlers.

Only file cleanup lives here: photos on disk have no owner once their row is
gone. Image processing is deliberately not a post_save hook — it is queued
explicitly by the service layer after the transaction commits, so it never
re-enters save() or runs before the row exists for a worker.
"""
import logging

from django.db import transaction
from django.db.models.signals import post_delete
from django.dispatch import receiver

from .models import Complaint

logger = logging.getLogger('nagriksetu.signals')


@receiver(post_delete, sender=Complaint)
def delete_complaint_files(sender, instance, **kwargs):
    """Remove the photo and thumbnail after the delete commits."""
    def _cleanup():
        for field in (instance.image, instance.thumbnail):
            if not field:
                continue
            try:
                field.storage.delete(field.name)
            except Exception as exc:  # noqa: BLE001 - storage may be remote
                logger.warning('Could not delete %s: %s', field.name, exc)

    transaction.on_commit(_cleanup)
