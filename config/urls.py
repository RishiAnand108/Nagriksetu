"""Root URL configuration for NagrikSetu."""
from django.conf import settings
from django.contrib import admin
from django.urls import include, path, re_path
from django.views.static import serve

from core.ratelimit import login_throttled
from core.views import handler400, handler403, handler404, handler500, healthcheck  # noqa: F401

admin.site.site_header = 'NagrikSetu Administration'
admin.site.site_title = 'NagrikSetu'
admin.site.index_title = 'Operations'
# The admin sign-in gets the same brute-force protection as the main one.
admin.site.login = login_throttled(admin.site.login)

urlpatterns = [
    path('admin/', admin.site.urls),
    path('healthz/', healthcheck, name='healthcheck'),
    path('api/', include('api.urls')),
    path('users/', include('users.urls')),
    path('', include('complaints.urls')),
]

# Media is served by object storage in production. Django serves local media
# only in DEBUG, or when explicitly asked to for a single-instance demo.
if (settings.DEBUG or settings.SERVE_MEDIA_FROM_APP) and not settings.USE_OBJECT_STORAGE:
    media_prefix = settings.MEDIA_URL.lstrip('/')
    urlpatterns += [
        re_path(rf'^{media_prefix}(?P<path>.*)$', serve, {'document_root': settings.MEDIA_ROOT}),
    ]
