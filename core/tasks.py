# core/tasks.py
"""
Background jobs.

With no CELERY_BROKER_URL these run inline (CELERY_TASK_ALWAYS_EAGER), so the
call sites can always use `.delay()` and stop caring whether a worker exists.
Callers enqueue with transaction.on_commit, so a worker never reads a row
before it is committed.
"""
import logging
import smtplib

from celery import shared_task
from django.apps import apps
from django.conf import settings
from django.core.mail import send_mail

logger = logging.getLogger('nagriksetu.tasks')


@shared_task(ignore_result=True)
def process_complaint_image_task(complaint_id: int) -> bool:
    """Normalise, watermark and thumbnail a complaint photo off the request cycle."""
    from core.imaging import process_complaint_image

    Complaint = apps.get_model('complaints', 'Complaint')
    try:
        complaint = Complaint.objects.select_related('ward').get(pk=complaint_id)
    except Complaint.DoesNotExist:
        logger.warning('Image task skipped — complaint %s no longer exists', complaint_id)
        return False
    return process_complaint_image(complaint)


@shared_task(
    bind=True,
    ignore_result=True,
    autoretry_for=(smtplib.SMTPException, OSError),
    retry_backoff=30,
    max_retries=3,
)
def send_email_task(self, subject: str, body: str, recipients: list[str]) -> None:
    """Send a plain-text email; transient SMTP/network failures are retried with backoff."""
    send_mail(subject, body, settings.DEFAULT_FROM_EMAIL, recipients, fail_silently=False)
    logger.info('Email sent: %r to %d recipient(s)', subject, len(recipients))
