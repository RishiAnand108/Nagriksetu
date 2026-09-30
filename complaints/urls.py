# complaints/urls.py
from django.urls import path

from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('dashboard/', views.dashboard, name='dashboard'),
    path('operations/', views.corporator_dashboard, name='corporator-dashboard'),
    path('map/', views.ComplaintMapView.as_view(), name='complaint-map'),
    path('map/data/', views.map_data, name='complaint-map-data'),

    path('complaints/', views.ComplaintListView.as_view(), name='complaint-list'),
    path('complaints/new/', views.ComplaintCreateView.as_view(), name='complaint-create'),
    path('complaints/<int:pk>/', views.ComplaintDetailView.as_view(), name='complaint-detail'),
    path('complaints/<int:pk>/edit/', views.ComplaintEditView.as_view(), name='complaint-edit'),
    path('complaints/<int:pk>/delete/', views.delete_complaint, name='complaint-delete'),
    path('complaints/<int:pk>/comment/', views.add_comment, name='complaint-comment'),
    path('complaints/<int:pk>/upvote/', views.toggle_upvote, name='complaint-upvote'),
    path('complaints/<int:pk>/status/', views.update_status, name='update-status'),
    path('complaints/<int:pk>/handling/', views.update_handling, name='update-handling'),
]
