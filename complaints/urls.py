# complaints/urls.py
from django.urls import path
from . import views

urlpatterns = [
    path('',                        views.ComplaintListView.as_view(),   name='complaint-list'),
    path('<int:pk>/',               views.ComplaintDetailView.as_view(), name='complaint-detail'),
    path('create/',                 views.ComplaintCreateView.as_view(), name='complaint-create'),
    path('dashboard/',              views.corporator_dashboard,          name='corporator-dashboard'),
    path('update-status/<int:pk>/', views.update_status,                 name='update-status'),
]