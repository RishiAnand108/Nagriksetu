# complaints/api.py
"""REST API for complaints — ViewSets, wired up by api/urls.py."""
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema, extend_schema_view
from rest_framework import status as http
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.viewsets import ModelViewSet, ReadOnlyModelViewSet

from core.exceptions import Conflict
from core.permissions import ComplaintAccess, IsCorporator

from . import policies, services
from .filters import ComplaintFilter
from .models import Complaint, Ward
from .serializers import (
    CommentSerializer,
    ComplaintDetailSerializer,
    ComplaintListSerializer,
    ComplaintStatsSerializer,
    ComplaintWriteSerializer,
    HandlingSerializer,
    StatusChangeSerializer,
    StatusHistorySerializer,
    WardSerializer,
)

ERRORS = {
    400: OpenApiResponse(description='Validation error — `{detail, code, errors}`'),
    403: OpenApiResponse(description='Authenticated but not allowed — `{detail, code}`'),
    404: OpenApiResponse(description='Not found, or outside your visibility scope'),
}


@extend_schema_view(
    list=extend_schema(
        summary='List complaints',
        description=(
            'Complaints visible to the caller: citizens see their own plus their home ward\'s; '
            'ward corporators see their ward plus unrouted complaints; city-wide corporators see all. '
            'Reporter identity is hidden on other residents\' complaints.'
        ),
        parameters=[
            OpenApiParameter('search', str, description='Free-text search over title, description and address.'),
            OpenApiParameter('ordering', str, description='created_at, updated_at, priority, upvote_count, status '
                                                          '(prefix with - for descending).'),
        ],
    ),
    retrieve=extend_schema(
        summary='Retrieve one complaint',
        description='Includes the conversation, the audit trail and a `permissions` block describing '
                    'which actions the caller may take.',
        responses={200: ComplaintDetailSerializer, 404: ERRORS[404]},
    ),
    create=extend_schema(
        summary='File a new complaint',
        description='multipart/form-data when attaching a photo (JPEG/PNG/WebP, size-limited). '
                    'Status, priority and assignment are server-controlled.',
        responses={201: ComplaintListSerializer, 400: ERRORS[400]},
    ),
    update=extend_schema(summary='Replace a complaint\'s editable fields'),
    partial_update=extend_schema(
        summary='Edit a complaint',
        description='The reporter may edit while the complaint is still Submitted; '
                    'afterwards the record is evidence and returns 409. '
                    'A new photo is re-processed and the old files are removed.',
        responses={200: ComplaintWriteSerializer, 400: ERRORS[400], 409: OpenApiResponse(description='Already being handled')},
    ),
    destroy=extend_schema(
        summary='Delete a complaint',
        description='Reporter only, while still Submitted.',
        responses={204: None, 409: OpenApiResponse(description='Already being handled')},
    ),
)
class ComplaintViewSet(ModelViewSet):
    permission_classes = [IsAuthenticated, ComplaintAccess]
    filterset_class = ComplaintFilter
    search_fields = ['title', 'description', 'address']
    ordering_fields = ['created_at', 'updated_at', 'priority', 'upvote_count', 'status']
    ordering = ['-created_at']
    throttle_scope = 'complaint-write'

    def get_throttles(self):
        # Reads use the default user/anon rates; only writes get the tight scope.
        if self.request.method in ('POST', 'PUT', 'PATCH', 'DELETE'):
            return [ScopedRateThrottle()]
        return super().get_throttles()

    def get_queryset(self):
        user = self.request.user
        if not user.is_authenticated:
            return Complaint.objects.none()
        queryset = Complaint.objects.visible_to(user).annotated_for(user)
        if self.action in ('retrieve', 'status', 'handling'):
            queryset = queryset.with_detail()
        return queryset

    def get_serializer_class(self):
        if self.action in ('create', 'update', 'partial_update'):
            return ComplaintWriteSerializer
        if self.action == 'retrieve':
            return ComplaintDetailSerializer
        return ComplaintListSerializer

    def _detail(self, pk):
        complaint = self.get_queryset().get(pk=pk)
        return ComplaintDetailSerializer(complaint, context=self.get_serializer_context()).data

    def perform_update(self, serializer):
        complaint = serializer.instance
        if policies.is_owner(self.request.user, complaint) and not policies.can_edit(self.request.user, complaint):
            raise Conflict('This complaint is already being handled and can no longer be edited.')
        serializer.save()

    def perform_destroy(self, instance):
        if not policies.can_delete(self.request.user, instance):
            raise Conflict('This complaint is already being handled and can no longer be deleted.')
        services.delete_complaint(instance)

    # ── Custom actions ────────────────────────────────────
    @extend_schema(
        summary='Change complaint status',
        description=(
            'Corporators responsible for the complaint only. Allowed moves: '
            'submitted → seen/in_progress/resolved/rejected; seen → in_progress/resolved/rejected; '
            'in_progress → resolved/rejected; resolved → in_progress (reopen); rejected → seen/in_progress. '
            'Every move is written to the audit trail and emails a verified reporter.'
        ),
        request=StatusChangeSerializer,
        responses={200: ComplaintDetailSerializer, 400: ERRORS[400], 403: ERRORS[403]},
    )
    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated, IsCorporator, ComplaintAccess])
    def status(self, request, pk=None):
        complaint = self.get_object()
        serializer = StatusChangeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            services.change_status(
                complaint,
                new_status=serializer.validated_data['status'],
                actor=request.user,
                note=serializer.validated_data.get('note', ''),
            )
        except services.TransitionError as exc:
            raise ValidationError({'status': [str(exc)]}, code='invalid_transition')
        return Response(self._detail(complaint.pk))

    @extend_schema(
        summary='Triage: set priority, assignee or ward',
        description='Corporators responsible for the complaint only. Each change is audited. '
                    'Assignees must be corporators serving the complaint\'s ward (or city-wide).',
        request=HandlingSerializer,
        responses={200: ComplaintDetailSerializer, 400: ERRORS[400], 403: ERRORS[403]},
    )
    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated, IsCorporator, ComplaintAccess])
    def handling(self, request, pk=None):
        complaint = self.get_object()
        serializer = HandlingSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        changes = {k: data[k] for k in ('priority', 'assigned_to', 'ward') if k in data}
        try:
            services.update_handling(complaint, actor=request.user, note=data.get('note', ''), **changes)
        except services.HandlingError as exc:
            raise ValidationError({'non_field_errors': [str(exc)]})
        return Response(self._detail(complaint.pk))

    @extend_schema(
        summary='Toggle "this affects me too"',
        description='Any resident who can see the complaint, except its reporter. One vote per person.',
        request=None,
        responses={200: {'type': 'object', 'properties': {
            'upvoted': {'type': 'boolean'}, 'count': {'type': 'integer'},
        }}, 403: ERRORS[403]},
    )
    @action(detail=True, methods=['post'])
    def upvote(self, request, pk=None):
        complaint = self.get_object()
        upvoted, count = services.toggle_upvote(complaint, user=request.user)
        return Response({'upvoted': upvoted, 'count': count})

    @extend_schema(
        methods=['GET'], summary='List comments', responses=CommentSerializer(many=True),
    )
    @extend_schema(
        methods=['POST'], summary='Add a comment',
        description='The reporter and responsible corporators only. Corporator comments are marked official '
                    'and notify the reporter.',
        request=CommentSerializer, responses={201: CommentSerializer, 400: ERRORS[400], 403: ERRORS[403]},
    )
    @action(detail=True, methods=['get', 'post'])
    def comments(self, request, pk=None):
        complaint = self.get_object()
        if request.method == 'GET':
            queryset = complaint.comments.select_related('author')
            return Response(CommentSerializer(queryset, many=True).data)

        serializer = CommentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        comment = services.add_comment(complaint, author=request.user, body=serializer.validated_data['body'])
        return Response(CommentSerializer(comment).data, status=http.HTTP_201_CREATED)

    @extend_schema(summary='Audit trail for one complaint', responses=StatusHistorySerializer(many=True))
    @action(detail=True, methods=['get'])
    def history(self, request, pk=None):
        complaint = self.get_object()
        queryset = complaint.history.select_related('changed_by')
        return Response(StatusHistorySerializer(queryset, many=True).data)

    @extend_schema(
        summary='Aggregate counts across everything you can see',
        parameters=[OpenApiParameter('ward', OpenApiTypes.INT, description='Limit to one ward.')],
        responses=ComplaintStatsSerializer,
    )
    @action(detail=False, methods=['get'], pagination_class=None, filter_backends=[])
    def stats(self, request):
        queryset = Complaint.objects.visible_to(request.user)
        ward = request.query_params.get('ward')
        if ward and ward.isdigit():
            queryset = queryset.filter(ward_id=int(ward))
        return Response(services.dashboard_stats(queryset))


@extend_schema_view(
    list=extend_schema(summary='List municipal wards'),
    retrieve=extend_schema(summary='Retrieve one ward'),
)
class WardViewSet(ReadOnlyModelViewSet):
    queryset = Ward.objects.all()
    serializer_class = WardSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = None
    search_fields = ['name', 'city']
