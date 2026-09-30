# complaints/signals.py
"""
Signal handlers.

Image processing is deliberately NOT wired to post_save any more. The old
handler re-entered save() from inside a save(), which meant every complaint was
written twice and the watermark ran synchronously inside the request. Creation
now queues the job explicitly in complaints.services.create_complaint.

What remains here is cleanup: files on disk have no owner once their row is
gone, so deleting a complaint deletes its photos too.
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
