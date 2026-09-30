# config/__init__.py
# Import the Celery app so shared_task decorators bind to it at startup.
# Celery is an optional convenience here — a missing install must not stop
# the site from booting.
try:
    from .celery import app as celery_app

    __all__ = ('celery_app',)
except ImportError:  # pragma: no cover - only hit when celery is absent
    celery_app = None
    __all__ = ()
