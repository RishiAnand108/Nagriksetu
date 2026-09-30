# config/celery.py
"""
Celery application.

The broker is optional. When CELERY_BROKER_URL is unset, base settings turn on
CELERY_TASK_ALWAYS_EAGER, so `.delay()` executes inline and the project runs
with nothing but `manage.py runserver`. Set the broker and start a worker to
move image processing off the request cycle:

    celery -A config worker --loglevel=info
"""
import os

from celery import Celery

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

app = Celery('nagriksetu')
app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks()

