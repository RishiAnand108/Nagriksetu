# complaints/apps.py
from django.apps import AppConfig


class ComplaintsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'complaints'

    def ready(self):
        # Imported for its side effect: registers the post_delete file cleanup.
        from . import signals  # noqa: F401
