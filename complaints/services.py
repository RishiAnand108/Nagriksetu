# complaints/services.py
"""
Business rules for complaints.

Views (HTML and API alike) and the admin call into here rather than mutating
models directly, so a status or handling change always writes its audit row
and fires its notification — no matter which entry point triggered it.
"""
from __future__ import annotations

import logging

from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.models import Count, Q
from django.template.loader import render_to_string
from django.utils import timezone

from users.models import Role

from .models import (
    ALLOWED_TRANSITIONS,
    CLOSED_STATUSES,
    Comment,
    Complaint,
    EventKind,
    IssueType,
    Priority,
    Status,
    StatusHistory,
    Upvote,
    Ward,
)

from .policies import is_corporator

logger = logging.getLogger('nagriksetu.services')

# Fields a citizen (or corporator, via the API) may edit on the report itself.
EDITABLE_FIELDS = ('issue_type', 'title', 'description', 'address', 'latitude', 'longitude', 'ward')

_UNSET = object()


class WorkflowError(ValueError):
    """Base class for rule violations the caller should show to the user."""


class TransitionError(WorkflowError):
    """Raised when a requested status change is not permitted."""


class HandlingError(WorkflowError):
    """Raised when a priority / assignment / ward change is not permitted."""


# ── Coordinates & wards ───────────────────────────────────
def _parse_coord(raw, lo: float, hi: float) -> float:
    """
    Coerce a posted coordinate to a float inside its valid range.

    A denied GPS prompt posts an empty string; anything unparseable or out of
    range degrades to 0.0 (the "no location" sentinel) instead of a 500.
    """
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return 0.0
    if value != value or value in (float('inf'), float('-inf')):  # NaN / inf
        return 0.0
    return value if lo <= value <= hi else 0.0


def parse_latitude(raw) -> float:
    return _parse_coord(raw, -90.0, 90.0)


def parse_longitude(raw) -> float:
    return _parse_coord(raw, -180.0, 180.0)


def nearest_ward(latitude: float, longitude: float) -> Ward | None:
    """
    Placeholder ward resolution.

    Real deployments would hit a GIS boundary lookup. Until then we only assign
    a ward when exactly one exists, which keeps single-ward pilots working
    without inventing wrong data for multi-ward cities.
    """
    if not (latitude or longitude):
        return None
    wards = list(Ward.objects.all()[:2])
    return wards[0] if len(wards) == 1 else None


# ── Filing and editing ────────────────────────────────────
@transaction.atomic
def create_complaint(*, user, form_data, latitude, longitude, image=None) -> Complaint:
    """Create a complaint, seed its history, and queue image processing."""
    complaint = Complaint(
        user=user,
        issue_type=form_data['issue_type'],
        title=form_data.get('title', ''),
        description=form_data.get('description', ''),
        address=form_data.get('address', ''),
        latitude=latitude,
        longitude=longitude,
    )
    if image is not None:
        complaint.image = image
    complaint.ward = form_data.get('ward') or nearest_ward(latitude, longitude) or getattr(user, 'ward', None)
    complaint.save()

    complaint.history.create(
        changed_by=user,
        old_status='',
        new_status=complaint.status,
        note='Complaint filed.',
    )

    if complaint.image:
        _queue_image_processing_on_commit(complaint.pk)

    logger.info('Complaint %s created by %s', complaint.pk, user.username)
    return complaint


@transaction.atomic
def update_complaint(complaint: Complaint, *, changes: dict) -> Complaint:
    """
    Apply edits to the report. A replaced photo goes back through the same
    pipeline as a new one, and the previous files are removed once committed.
    """
    for field in EDITABLE_FIELDS:
        if field in changes:
            value = changes[field]
            if field == 'latitude':
                value = parse_latitude(value)
            elif field == 'longitude':
                value = parse_longitude(value)
            setattr(complaint, field, value)

    new_image = changes.get('image')
    if new_image:
        # Read the stored names from the database: a ModelForm has already
        # put the new upload on the instance by the time we get here.
        stored = Complaint.objects.filter(pk=complaint.pk).values_list('image', 'thumbnail').first() or ()
        stale = [name for name in stored if name]
        storage = complaint.image.storage
        complaint.image = new_image
        complaint.thumbnail = ''
        complaint.image_processed = False
        transaction.on_commit(lambda: _delete_files(storage, stale))

    complaint.save()

    if new_image:
        _queue_image_processing_on_commit(complaint.pk)
    return complaint


def delete_complaint(complaint: Complaint) -> None:
    """Files are cleaned up by the post_delete signal after commit."""
    logger.info('Complaint %s deleted', complaint.pk)
    complaint.delete()


def _delete_files(storage, names) -> None:
    for name in names:
        try:
            storage.delete(name)
        except Exception as exc:  # noqa: BLE001 - storage may be remote
            logger.warning('Could not delete %s: %s', name, exc)


def _queue_image_processing_on_commit(complaint_id: int) -> None:
    # A worker must never pick the job up before the row it reads is committed.
    transaction.on_commit(lambda: queue_image_processing(complaint_id))


def queue_image_processing(complaint_id: int) -> None:
    """
    Hand the photo to Celery, or process inline if the queue is unreachable.

    A broker outage should slow a complaint down, never reject it.
    """
    from core.tasks import process_complaint_image_task

    try:
        process_complaint_image_task.delay(complaint_id)
    except Exception as exc:  # noqa: BLE001 - broker may simply be down
        logger.warning('Celery unavailable (%s); processing image inline', exc)
        try:
            process_complaint_image_task.apply(args=[complaint_id])
        except Exception:  # noqa: BLE001
            logger.exception('Inline image processing failed for complaint %s', complaint_id)


# ── Workflow ──────────────────────────────────────────────
@transaction.atomic
def change_status(complaint: Complaint, *, new_status: str, actor, note: str = '') -> Complaint:
    """
    Move a complaint to a new status, recording who did it and why.

    The row is locked for the duration so two officials acting at once cannot
    both transition from the same starting state.
    """
    valid = {choice.value for choice in Status}
    if new_status not in valid:
        raise TransitionError(f'"{new_status}" is not a valid status.')

    current = Complaint.objects.select_for_update().only('status').get(pk=complaint.pk).status
    complaint.status = current
    old_status = current

    if new_status == old_status:
        raise TransitionError(f'Complaint is already {complaint.get_status_display()}.')

    if new_status not in ALLOWED_TRANSITIONS.get(old_status, set()):
        raise TransitionError(
            f'Cannot move from {complaint.get_status_display()} to {Status(new_status).label}.'
        )

    complaint.status = new_status
    complaint.resolved_at = timezone.now() if new_status in CLOSED_STATUSES else None
    if complaint.assigned_to_id is None and getattr(actor, 'role', '') == Role.CORPORATOR:
        complaint.assigned_to = actor
    complaint.save(update_fields=['status', 'resolved_at', 'assigned_to', 'updated_at'])

    complaint.history.create(
        changed_by=actor,
        kind=EventKind.STATUS,
        old_status=old_status,
        new_status=new_status,
        note=note[:255],
    )

    _notify_reporter(
        complaint,
        subject=f'Complaint #{complaint.pk} is now {complaint.get_status_display()}',
        template='emails/status_changed.txt',
        context={'old_status': Status(old_status).label, 'note': note},
    )

    logger.info(
        'Complaint %s: %s → %s by %s', complaint.pk, old_status, new_status,
        getattr(actor, 'username', 'system'),
    )
    return complaint


@transaction.atomic
def update_handling(complaint: Complaint, *, actor, priority=_UNSET, assigned_to=_UNSET,
                    ward=_UNSET, note: str = '') -> list[str]:
    """
    Change priority, assignee and/or ward, writing one audit event per change.

    Returns human-readable descriptions of what changed (empty if nothing did).
    """
    events: list[tuple[str, str]] = []
    suffix = f' — {note.strip()}' if note and note.strip() else ''

    if priority is not _UNSET and priority is not None and int(priority) != complaint.priority:
        if int(priority) not in Priority.values:
            raise HandlingError('Unknown priority.')
        old = complaint.get_priority_display()
        complaint.priority = int(priority)
        events.append((EventKind.PRIORITY, f'Priority {old} → {complaint.get_priority_display()}'))

    if ward is not _UNSET and ward != complaint.ward:
        old = str(complaint.ward) if complaint.ward else 'Unrouted'
        complaint.ward = ward
        events.append((EventKind.WARD, f'Moved from {old} to {ward or "Unrouted"}'))
        # A transfer hands the complaint to the new ward's office.
        if complaint.assigned_to and complaint.assigned_to.ward_id not in (None, getattr(ward, 'pk', None)):
            events.append((EventKind.ASSIGNMENT, f'Unassigned {complaint.assigned_to.display_name} (ward transfer)'))
            complaint.assigned_to = None

    if assigned_to is not _UNSET and assigned_to != complaint.assigned_to:
        if assigned_to is not None:
            if not is_corporator(assigned_to):
                raise HandlingError('Complaints can only be assigned to corporators.')
            if assigned_to.ward_id and complaint.ward_id and assigned_to.ward_id != complaint.ward_id:
                raise HandlingError(f'{assigned_to.username} does not serve {complaint.ward}.')
        complaint.assigned_to = assigned_to
        who = assigned_to.display_name if assigned_to else 'nobody'
        events.append((EventKind.ASSIGNMENT, f'Assigned to {who}'))

    if not events:
        return []

    complaint.save(update_fields=['priority', 'ward', 'assigned_to', 'updated_at'])
    StatusHistory.objects.bulk_create([
        StatusHistory(
            complaint=complaint, changed_by=actor, kind=kind,
            old_status=complaint.status, new_status=complaint.status,
            note=(text + suffix)[:255],
        )
        for kind, text in events
    ])
    logger.info('Complaint %s handling changed by %s: %s', complaint.pk, actor, events)
    return [text for _, text in events]


def assignable_corporators(complaint: Complaint):
    """Corporators who serve this complaint's ward (or the whole city)."""
    from users.models import CustomUser

    qs = CustomUser.objects.filter(role=Role.CORPORATOR, is_active=True).select_related('ward')
    if complaint.ward_id:
        qs = qs.filter(Q(ward_id=complaint.ward_id) | Q(ward__isnull=True))
    return qs


# ── Conversation & signals ────────────────────────────────
def add_comment(complaint: Complaint, *, author, body: str) -> Comment:
    comment = Comment.objects.create(complaint=complaint, author=author, body=body.strip())
    if comment.is_official and complaint.user_id != author.pk:
        _notify_reporter(
            complaint,
            subject=f'New reply on complaint #{complaint.pk}',
            template='emails/official_reply.txt',
            context={'comment': comment},
        )
    return comment


def toggle_upvote(complaint: Complaint, *, user) -> tuple[bool, int]:
    """
    Add or remove this user's upvote. Returns (now_upvoted, total).

    The unique constraint makes a racing double-click harmless.
    """
    try:
        with transaction.atomic():
            Upvote.objects.create(complaint=complaint, user=user)
        upvoted = True
    except IntegrityError:
        Upvote.objects.filter(complaint=complaint, user=user).delete()
        upvoted = False
    return upvoted, complaint.upvotes.count()


def _notify_reporter(complaint: Complaint, *, subject: str, template: str, context: dict) -> None:
    """Email the reporter after the surrounding transaction commits."""
    reporter = complaint.user
    if not reporter.can_receive_email:
        return

    body = render_to_string(template, {
        'complaint': complaint,
        'site_name': settings.SITE_NAME,
        'site_url': settings.SITE_URL,
        **context,
    })
    full_subject = f'[{settings.SITE_NAME}] {subject}'
    recipient = reporter.email

    def _send():
        from core.tasks import send_email_task
        try:
            send_email_task.delay(full_subject, body, [recipient])
        except Exception as exc:  # noqa: BLE001
            logger.warning('Could not queue email for complaint %s: %s', complaint.pk, exc)

    transaction.on_commit(_send)


# ── Reporting ─────────────────────────────────────────────
def dashboard_stats(queryset=None) -> dict:
    """Status counts for a dashboard in a single conditional aggregate."""
    qs = Complaint.objects.all() if queryset is None else queryset
    stats = qs.aggregate(
        total=Count('id'),
        submitted=Count('id', filter=Q(status=Status.SUBMITTED)),
        seen=Count('id', filter=Q(status=Status.SEEN)),
        in_progress=Count('id', filter=Q(status=Status.IN_PROGRESS)),
        resolved=Count('id', filter=Q(status=Status.RESOLVED)),
        rejected=Count('id', filter=Q(status=Status.REJECTED)),
        urgent_open=Count('id', filter=Q(priority__gte=Priority.HIGH) & ~Q(status__in=CLOSED_STATUSES)),
    )
    stats['pending'] = stats['submitted'] + stats['seen']
    stats['open'] = stats['total'] - stats['resolved'] - stats['rejected']
    stats['resolution_rate'] = (
        round(stats['resolved'] / stats['total'] * 100) if stats['total'] else 0
    )
    return stats


def issue_type_breakdown(queryset=None) -> list[dict]:
    """Complaint counts per issue type, largest first."""
    qs = Complaint.objects.all() if queryset is None else queryset
    counts = dict(qs.order_by().values_list('issue_type').annotate(n=Count('id')).values_list('issue_type', 'n'))
    rows = [
        {'key': value, 'label': label, 'count': counts.get(value, 0)}
        for value, label in IssueType.choices
        if counts.get(value, 0)
    ]
    return sorted(rows, key=lambda r: -r['count'])


def recent_activity(queryset, limit: int = 8):
    """Latest audit events across a set of complaints."""
    return (
        StatusHistory.objects.filter(complaint__in=queryset.values('pk'))
        .select_related('complaint', 'changed_by')
        .order_by('-created_at')[:limit]
    )

