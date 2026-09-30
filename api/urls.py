# api/urls.py
from django.urls import include, path
from django.utils.csp import CSP
from django.views.decorators.csp import csp_override
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularRedocView,
    SpectacularSwaggerView,
)
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenVerifyView

from complaints.api import ComplaintViewSet, WardViewSet
from users.api import (
    LegacyLoginAPIView,
    LegacyRefreshAPIView,
    LoginAPIView,
    LogoutAPIView,
    MeAPIView,
    RefreshAPIView,
    RegisterAPIView,
)

router = DefaultRouter()
router.register('complaints', ComplaintViewSet, basename='complaint')
router.register('wards', WardViewSet, basename='ward')

# Swagger UI and ReDoc load their bundles from jsDelivr and bootstrap with an
# inline script, so these two pages get a looser policy than the rest of the site.
DOCS_CSP = {
    'default-src': [CSP.SELF],
    'script-src': [CSP.SELF, CSP.UNSAFE_INLINE, 'https://cdn.jsdelivr.net'],
    'style-src': [CSP.SELF, CSP.UNSAFE_INLINE, 'https://cdn.jsdelivr.net', 'https://fonts.googleapis.com'],
    'font-src': [CSP.SELF, 'https://fonts.gstatic.com', 'data:'],
    'img-src': [CSP.SELF, 'data:', 'https://cdn.jsdelivr.net', 'https://cdn.redoc.ly'],
    'worker-src': [CSP.SELF, 'blob:'],
    'connect-src': [CSP.SELF],
    'frame-ancestors': [CSP.NONE],
}

urlpatterns = [
    # ── Auth ──────────────────────────────────────────────
    path('auth/register/', RegisterAPIView.as_view(), name='api-register'),
    path('auth/me/', MeAPIView.as_view(), name='api-me'),
    path('auth/token/', LoginAPIView.as_view(), name='token_obtain_pair'),
    path('auth/token/refresh/', RefreshAPIView.as_view(), name='token_refresh'),
    path('auth/token/verify/', TokenVerifyView.as_view(), name='token_verify'),
    path('auth/logout/', LogoutAPIView.as_view(), name='api-logout'),

    # Deprecated aliases, kept so existing clients do not break.
    path('token/', LegacyLoginAPIView.as_view(), name='token_obtain_pair_legacy'),
    path('token/refresh/', LegacyRefreshAPIView.as_view(), name='token_refresh_legacy'),

    # ── Docs ──────────────────────────────────────────────
    path('schema/', SpectacularAPIView.as_view(), name='schema'),
    path('docs/', csp_override(DOCS_CSP)(SpectacularSwaggerView.as_view(url_name='schema')), name='swagger-ui'),
    path('redoc/', csp_override(DOCS_CSP)(SpectacularRedocView.as_view(url_name='schema')), name='redoc'),

    # ── Resources ─────────────────────────────────────────
    path('', include(router.urls)),
]
