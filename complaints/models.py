# complaints/models.py
from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Count, Exists, IntegerField, OuterRef, Prefetch, Q, Subquery, Value
from django.db.models.functions import Coalesce
from django.urls import reverse
from django.utils import timezone

from users.models import Role


class IssueType(models.TextChoices):
    GARBAGE = 'garbage', 'Garbage'
    ROAD = 'road', 'Road Damage'
    WATER = 'water', 'Water Supply'
    STREETLIGHT = 'streetlight', 'Streetlight'
    DRAINAGE = 'drainage', 'Drainage / Sewage'
    STRAY = 'stray', 'Stray Animals'
    ENCROACHMENT = 'encroachment', 'Encroachment'
    OTHER = 'other', 'Other'


class Status(models.TextChoices):
    SUBMITTED = 'submitted', 'Submitted'
    # The stored value stays "seen" so existing API clients keep working.
    SEEN = 'seen', 'Acknowledged'
    IN_PROGRESS = 'in_progress', 'In Progress'
    RESOLVED = 'resolved', 'Resolved'
    REJECTED = 'rejected', 'Rejected'


# Statuses that count as "no longer active work".
CLOSED_STATUSES = {Status.RESOLVED, Status.REJECTED}
# Waiting on the municipality to start work.
PENDING_STATUSES = {Status.SUBMITTED, Status.SEEN}

# Which moves a corporator is allowed to make from a given status. Enforced in
# complaints.services.change_status so the rule lives in exactly one place.
ALLOWED_TRANSITIONS = {
    Status.SUBMITTED: {Status.SEEN, Status.IN_PROGRESS, Status.RESOLVED, Status.REJECTED},
    Status.SEEN: {Status.IN_PROGRESS, Status.RESOLVED, Status.REJECTED},
    Status.IN_PROGRESS: {Status.RESOLVED, Status.REJECTED},
    Status.RESOLVED: {Status.IN_PROGRESS},
    Status.REJECTED: {Status.SEEN, Status.IN_PROGRESS},
}


class Priority(models.IntegerChoices):
    LOW = 1, 'Low'
    NORMAL = 2, 'Normal'
    HIGH = 3, 'High'
    URGENT = 4, 'Urgent'


class Ward(models.Model):
    """A municipal ward — the unit a corporator is accountable for."""

    number = models.PositiveIntegerField(unique=True)
    name = models.CharField(max_length=80)
    city = models.CharField(max_length=80, default='Pune')

    class Meta:
        ordering = ['number']

    def __str__(self):
        return f'Ward {self.number} — {self.name}'


def _related_count(model):
    """Correlated COUNT subquery — avoids the row fan-out of joining two reverse FKs."""
    counts = (
        model.objects.filter(complaint=OuterRef('pk'))
        .order_by()
        .values('complaint')
        .annotate(n=Count('pk'))
        .values('n')
    )
    return Coalesce(Subquery(counts, output_field=IntegerField()), Value(0))


class ComplaintQuerySet(models.QuerySet):
    def visible_to(self, user):
        """
        The single visibility rule every entry point (HTML, API, map) builds on.

        - Citizens see their own reports, plus every report in their home ward
          (the ward feed that makes "this affects me too" meaningful).
        - Corporators see their ward plus complaints not yet routed to a ward.
          A corporator with no ward is a city-wide officer and sees everything.
        """
        if not user.is_authenticated:
            return self.none()
        if getattr(user, 'role', '') == Role.CORPORATOR:
            if user.ward_id:
                return self.filter(Q(ward_id=user.ward_id) | Q(ward__isnull=True))
            return self
        scope = Q(user=user)
        if user.ward_id:
            scope |= Q(ward_id=user.ward_id)
        return self.filter(scope)

    def open(self):
        return self.exclude(status__in=CLOSED_STATUSES)

    def with_related(self):
        return self.select_related('user', 'ward', 'assigned_to')

    def annotated_for(self, user):
        """Upvote/comment counts and the viewer's own vote, in the same query."""
        return self.with_related().annotate(
            upvote_count=_related_count(Upvote),
            comment_count=_related_count(Comment),
            has_upvoted=Exists(Upvote.objects.filter(complaint=OuterRef('pk'), user_id=user.pk)),
        )

    def with_detail(self):
        """Prefetch the conversation and audit trail with their authors (no N+1)."""
        return self.prefetch_related(
            Prefetch('comments', queryset=Comment.objects.select_related('author')),
            Prefetch('history', queryset=StatusHistory.objects.select_related('changed_by')),
        )


class Complaint(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='complaints',
    )
    issue_type = models.CharField(max_length=20, choices=IssueType.choices, db_index=True)
    title = models.CharField(max_length=120, blank=True)
    description = models.TextField(blank=True)

    image = models.ImageField(upload_to='complaints/%Y/%m/', blank=True)
    thumbnail = models.ImageField(upload_to='complaints/%Y/%m/thumbs/', blank=True)
    image_processed = models.BooleanField(default=False)

    latitude = models.FloatField(
        default=0.0,
        validators=[MinValueValidator(-90.0), MaxValueValidator(90.0)],
    )
    longitude = models.FloatField(
        default=0.0,
        validators=[MinValueValidator(-180.0), MaxValueValidator(180.0)],
    )
    address = models.CharField(max_length=255, blank=True)
    ward = models.ForeignKey(
        Ward,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='complaints',
    )

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.SUBMITTED,
        db_index=True,
    )
    priority = models.IntegerField(choices=Priority.choices, default=Priority.NORMAL, db_index=True)
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='assigned_complaints',
        limit_choices_to={'role': Role.CORPORATOR},
    )

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    objects = ComplaintQuerySet.as_manager()

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status', '-created_at'], name='cmp_status_created_idx'),
            models.Index(fields=['user', '-created_at'], name='cmp_user_created_idx'),
            models.Index(fields=['ward', 'status'], name='cmp_ward_status_idx'),
        ]

    def __str__(self):
        return f'#{self.pk} {self.get_issue_type_display()} — {self.get_status_display()}'

    def get_absolute_url(self):
        return reverse('complaint-detail', args=[self.pk])

    # ── Derived properties ────────────────────────────────
    @property
    def headline(self) -> str:
        """Title if the citizen gave one, else a sensible fallback."""
        if self.title:
            return self.title
        if self.description:
            return self.description[:60] + ('…' if len(self.description) > 60 else '')
        return self.get_issue_type_display()

    @property
    def is_closed(self) -> bool:
        return self.status in CLOSED_STATUSES

    @property
    def has_location(self) -> bool:
        # 0,0 is the "no fix" sentinel written when GPS was unavailable.
        return bool(self.latitude or self.longitude)

    @property
    def is_high_priority(self) -> bool:
        return self.priority >= Priority.HIGH

    @property
    def age_days(self) -> int:
        if not self.created_at:
            return 0
        end = self.resolved_at or timezone.now()
        return (end - self.created_at).days

    @property
    def status_css(self) -> str:
        """Maps a status onto the badge modifier used in static/css/app.css."""
        return {
            Status.SUBMITTED: 'warn',
            Status.SEEN: 'info',
            Status.IN_PROGRESS: 'progress',
            Status.RESOLVED: 'ok',
            Status.REJECTED: 'danger',
        }.get(self.status, 'info')

    def allowed_next_statuses(self):
        """Status values a corporator may move this complaint to right now."""
        return sorted(ALLOWED_TRANSITIONS.get(self.status, set()))

    def allowed_next_choices(self):
        """The same transitions as (value, label) pairs, for form widgets."""
        allowed = ALLOWED_TRANSITIONS.get(self.status, set())
        return [(value, label) for value, label in Status.choices if value in allowed]


class EventKind(models.TextChoices):
    STATUS = 'status', 'Status change'
    PRIORITY = 'priority', 'Priority change'
    ASSIGNMENT = 'assignment', 'Assignment'
    WARD = 'ward', 'Ward transfer'


class StatusHistory(models.Model):
    """
    Append-only audit trail — who changed what, when, and why.

    Status moves carry old/new status. Handling changes (priority, assignment,
    ward) are recorded here too, with the complaint's status at that moment
    and a note describing the change, so there is one timeline to read.
    """

    complaint = models.ForeignKey(
        Complaint,
        on_delete=models.CASCADE,
        related_name='history',
    )
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='status_changes',
    )
    kind = models.CharField(max_length=20, choices=EventKind.choices, default=EventKind.STATUS)
    old_status = models.CharField(max_length=20, choices=Status.choices, blank=True)
    new_status = models.CharField(max_length=20, choices=Status.choices)
    note = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name_plural = 'status history'
        indexes = [
            models.Index(fields=['complaint', '-created_at'], name='hist_cmp_created_idx'),
        ]

    def __str__(self):
        if self.kind != EventKind.STATUS:
            return f'#{self.complaint_id}: {self.note}'
        return f'#{self.complaint_id}: {self.old_status or "new"} → {self.new_status}'

    @property
    def is_status_change(self) -> bool:
        return self.kind == EventKind.STATUS


class Comment(models.Model):
    """Conversation between the citizen who filed and the responding corporator."""

    complaint = models.ForeignKey(
        Complaint,
        on_delete=models.CASCADE,
        related_name='comments',
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='comments',
    )
    body = models.TextField(max_length=1000)
    is_official = models.BooleanField(
        default=False,
        help_text='Set automatically when the author is a corporator.',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']
        indexes = [
            models.Index(fields=['complaint', 'created_at'], name='cmt_cmp_created_idx'),
        ]

    def __str__(self):
        return f'Comment by {self.author} on #{self.complaint_id}'

    def save(self, *args, **kwargs):
        self.is_official = getattr(self.author, 'role', '') == Role.CORPORATOR
        super().save(*args, **kwargs)


class Upvote(models.Model):
    """
    "This affects me too."

    The unique constraint is what makes the count trustworthy — one resident,
    one vote per complaint, enforced by the database rather than by a view.
    """

    complaint = models.ForeignKey(
        Complaint,
        on_delete=models.CASCADE,
        related_name='upvotes',
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='upvotes',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['complaint', 'user'], name='unique_upvote_per_user'),
        ]

    def __str__(self):
        return f'{self.user} upvoted #{self.complaint_id}'
