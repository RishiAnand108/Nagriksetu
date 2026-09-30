# core/context_processors.py
"""Values every template needs, injected once instead of per-view."""
from django.conf import settings

from complaints.policies import is_corporator


def site_context(request):
    user = getattr(request, 'user', None)
    return {
        'SITE_NAME': settings.SITE_NAME,
        'SITE_TAGLINE': settings.SITE_TAGLINE,
        'MAX_UPLOAD_SIZE_MB': settings.MAX_UPLOAD_SIZE_MB,
        'is_corporator': is_corporator(user),
    }
