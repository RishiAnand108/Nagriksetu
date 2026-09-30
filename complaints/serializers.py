# complaints/serializers.py
from rest_framework import serializers

from users.models import CustomUser, Role

from . import policies, rules, services
from .models import Comment, Complaint, Priority, Status, StatusHistory, Ward


class WardSerializer(serializers.ModelSerializer):
    label = serializers.CharField(source='__str__', read_only=True)

    class Meta:
        model = Ward
        fields = ['id', 'number', 'name', 'city', 'label']


class UserBriefSerializer(serializers.Serializer):
    """Minimal, safe projection of a user — never expose email or password state."""

    id = serializers.IntegerField(read_only=True)
    username = serializers.CharField(read_only=True)
    display_name = serializers.CharField(read_only=True)
    role = serializers.CharField(read_only=True)


class CommentSerializer(serializers.ModelSerializer):
    author = UserBriefSerializer(read_only=True)

    class Meta:
        model = Comment
        fields = ['id', 'author', 'body', 'is_official', 'created_at']
        read_only_fields = ['id', 'author', 'is_official', 'created_at']

    def validate_body(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError('Comment cannot be empty.')
        return value


class StatusHistorySerializer(serializers.ModelSerializer):
    changed_by = UserBriefSerializer(read_only=True)
    old_status_label = serializers.SerializerMethodField()
    new_status_label = serializers.CharField(source='get_new_status_display', read_only=True)

    class Meta:
        model = StatusHistory
        fields = [
            'id', 'kind', 'changed_by', 'old_status', 'old_status_label',
            'new_status', 'new_status_label', 'note', 'created_at',
        ]

    def get_old_status_label(self, obj) -> str:
        return Status(obj.old_status).label if obj.old_status else ''


class ComplaintListSerializer(serializers.ModelSerializer):
    """Compact projection for list endpoints."""

    user = serializers.SerializerMethodField()
    is_mine = serializers.SerializerMethodField()
    ward = WardSerializer(read_only=True)
    issue_type_label = serializers.CharField(source='get_issue_type_display', read_only=True)
    status_label = serializers.CharField(source='get_status_display', read_only=True)
    priority_label = serializers.CharField(source='get_priority_display', read_only=True)
    image = serializers.ImageField(use_url=True, read_only=True)
    thumbnail = serializers.ImageField(use_url=True, read_only=True)
    upvote_count = serializers.IntegerField(read_only=True)
    comment_count = serializers.IntegerField(read_only=True)
    has_upvoted = serializers.BooleanField(read_only=True)
    headline = serializers.CharField(read_only=True)
    age_days = serializers.IntegerField(read_only=True)

    class Meta:
        model = Complaint
        fields = [
            'id', 'user', 'is_mine', 'headline', 'title', 'issue_type', 'issue_type_label',
            'description', 'image', 'thumbnail', 'image_processed', 'latitude', 'longitude',
            'address', 'ward', 'status', 'status_label', 'priority', 'priority_label',
            'upvote_count', 'comment_count', 'has_upvoted', 'age_days',
            'created_at', 'updated_at', 'resolved_at',
        ]

    def _viewer(self):
        request = self.context.get('request')
        return getattr(request, 'user', None)

    def get_user(self, obj) -> dict | None:
        # Neighbours browsing the ward feed see the issue, not who reported it.
        if not policies.can_see_reporter(self._viewer(), obj):
            return None
        return UserBriefSerializer(obj.user).data

    def get_is_mine(self, obj) -> bool:
        return policies.is_owner(self._viewer(), obj)


class ComplaintDetailSerializer(ComplaintListSerializer):
    assigned_to = UserBriefSerializer(read_only=True)
    comments = CommentSerializer(many=True, read_only=True)
    history = StatusHistorySerializer(many=True, read_only=True)
    allowed_next_statuses = serializers.SerializerMethodField()
    permissions = serializers.SerializerMethodField()

    class Meta(ComplaintListSerializer.Meta):
        fields = ComplaintListSerializer.Meta.fields + [
            'assigned_to', 'comments', 'history', 'allowed_next_statuses', 'permissions',
        ]

    def get_allowed_next_statuses(self, obj) -> list[str]:
        return obj.allowed_next_statuses() if policies.can_manage(self._viewer(), obj) else []

    def get_permissions(self, obj) -> dict:
        """What the caller may do next — lets a client render the right buttons."""
        actions = policies.actions_for(self._viewer(), obj)
        return {k: v for k, v in actions.items() if k.startswith('can_')}


class ComplaintWriteSerializer(serializers.ModelSerializer):
    """
    Create/update serializer.

    status/priority/assigned_to are absent on purpose — a citizen must not be
    able to file a complaint that is already "resolved". Those move only
    through the /status/ and /handling/ actions.
    """

    class Meta:
        model = Complaint
        fields = [
            'issue_type', 'title', 'description', 'address',
            'image', 'latitude', 'longitude', 'ward',
        ]

    def validate_image(self, value):
        rules.validate_photo(value)
        return value

    def validate(self, attrs):
        # On a partial update, judge the complaint as it will look afterwards,
        # not just the fields present in this request.
        instance = self.instance
        description = attrs.get('description', getattr(instance, 'description', ''))
        image = attrs.get('image') or getattr(instance, 'image', None)
        rules.require_description_or_photo(description, image)
        return attrs

    def create(self, validated_data):
        request = self.context['request']
        image = validated_data.pop('image', None)
        return services.create_complaint(
            user=request.user,
            form_data=validated_data,
            latitude=services.parse_latitude(validated_data.get('latitude')),
            longitude=services.parse_longitude(validated_data.get('longitude')),
            image=image,
        )

    def update(self, instance, validated_data):
        return services.update_complaint(instance, changes=validated_data)


class StatusChangeSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=Status.choices)
    note = serializers.CharField(max_length=255, required=False, allow_blank=True)


class HandlingSerializer(serializers.Serializer):
    """Triage fields. Send only the ones you want to change."""

    priority = serializers.ChoiceField(choices=Priority.choices, required=False)
    assigned_to = serializers.PrimaryKeyRelatedField(
        queryset=CustomUser.objects.filter(role=Role.CORPORATOR, is_active=True),
        required=False, allow_null=True,
    )
    ward = serializers.PrimaryKeyRelatedField(queryset=Ward.objects.all(), required=False, allow_null=True)
    note = serializers.CharField(max_length=200, required=False, allow_blank=True)

    def validate(self, attrs):
        if not ({'priority', 'assigned_to', 'ward'} & attrs.keys()):
            raise serializers.ValidationError('Provide at least one of priority, assigned_to or ward.')
        return attrs


class ComplaintStatsSerializer(serializers.Serializer):
    """Shape of the /api/complaints/stats/ response."""

    total = serializers.IntegerField()
    submitted = serializers.IntegerField()
    seen = serializers.IntegerField()
    in_progress = serializers.IntegerField()
    resolved = serializers.IntegerField()
    rejected = serializers.IntegerField()
    pending = serializers.IntegerField()
    open = serializers.IntegerField()
    urgent_open = serializers.IntegerField()
    resolution_rate = serializers.IntegerField()
