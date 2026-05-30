from django.contrib import admin
from .models import Complaint

# Register your models here.
@admin.register(Complaint)

class ComplaintAdmin(admin.ModelAdmin):
    list_display=['id','issue_type','status','user','created_at']
    list_filter=['status','issue_type']
    search_fields=['user__username','description']
    ordering=['-created_at']
    readonly_fields=['latitude','longitude']