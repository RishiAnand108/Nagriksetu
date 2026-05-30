# complaints/serializers.py
from rest_framework import serializers
from .models import Complaint

class ComplaintSerializer(serializers.ModelSerializer):

    # show username instead of user id
    user        = serializers.StringRelatedField(read_only=True)
    # show human readable label instead of code
    issue_type  = serializers.CharField(source='get_issue_type_display', read_only=True)
    status      = serializers.CharField(source='get_status_display',     read_only=True)
    # full image URL
    image       = serializers.ImageField(use_url=True, read_only=True)

    class Meta:
        model  = Complaint
        fields = [
            'id',
            'user',
            'issue_type',
            'description',
            'image',
            'latitude',
            'longitude',
            'status',
            'created_at',
        ]