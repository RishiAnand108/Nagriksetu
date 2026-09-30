# core/views.py
"""Error pages and an operational health check."""
from django.conf import settings
from django.db import connection
from django.http import HttpResponseServerError, JsonResponse
from django.template import loader
from django.shortcuts import render


def healthcheck(request):
    """
    Readiness probe: the database must answer. The other fields describe how
    the instance is configured (never credentials) to make incidents quicker
    to diagnose.
    """
    try:
        with connection.cursor() as cursor:
            cursor.execute('SELECT 1')
            cursor.fetchone()
        database = 'ok'
    except Exception:  # noqa: BLE001
        database = 'unavailable'

    healthy = database == 'ok'
    return JsonResponse(
        {
            'status': 'ok' if healthy else 'degraded',
            'version': settings.APP_VERSION,
            'checks': {
                'database': database,
                'task_queue': 'inline' if settings.CELERY_TASK_ALWAYS_EAGER else 'celery',
                'media_storage': 'object-storage' if settings.USE_OBJECT_STORAGE else 'local-disk',
            },
        },
        status=200 if healthy else 503,
        headers={'Cache-Control': 'no-store'},
    )


def handler400(request, exception=None):
    return render(request, 'errors/400.html', status=400)


def handler403(request, exception=None):
    # PermissionDenied messages in this codebase are written for end users.
    message = str(exception) if exception is not None and getattr(exception, 'args', None) else ''
    return render(request, 'errors/403.html', {'exception': message}, status=403)


def handler404(request, exception=None):
    return render(request, 'errors/404.html', status=404)


def handler500(request):
    # Rendered without context processors: they may touch the database, which
    # could be exactly what is failing.
    html = loader.get_template('errors/500.html').render({'request_id': getattr(request, 'request_id', '')})
    return HttpResponseServerError(html)
