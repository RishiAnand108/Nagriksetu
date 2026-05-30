# complaints/apps.py
from django.apps import AppConfig

class ComplaintsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'complaints'

    def ready(self):
        import complaints.signals    # ← this MUST be here