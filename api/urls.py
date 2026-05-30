# api/urls.py
from django.urls import path
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from complaints.views import ComplaintListAPI, ComplaintDetailAPI

urlpatterns = [
    #jwt auth endoints
    path('token/',     TokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    #complaint endpoint
    path('complaints/',      ComplaintListAPI.as_view(),   name='api-complaint-list'),
    path('complaints/<int:pk>/', ComplaintDetailAPI.as_view(), name='api-complaint-detail'),
]