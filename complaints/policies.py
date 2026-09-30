# complaints/policies.py
"""
Who may do what to a complaint they can already see.

Visibility itself is ComplaintQuerySet.visible_to() — every view and API
endpoint fetches through it first, so an out-of-scope complaint is a 404
before any of these checks run. These functions answer the next question:
of the complaints you can see, which actions are yours to take. The HTML
views, the DRF permission class and the templates all ask here, so the rules
cannot drift apart.
"""
from users.models import Role

from .models import Status


def is_corporator(user) -> bool:
    return bool(user and user.is_authenticated and getattr(user, 'role', '') == Role.CORPORATOR)


def is_owner(user, complaint) -> bool:
    return bool(user and user.is_authenticated and complaint.user_id == user.pk)


def can_edit(user, complaint) -> bool:
    """A citizen may correct their report until the municipality acts on it."""
    return is_owner(user, complaint) and complaint.status == Status.SUBMITTED


can_delete = can_edit


def can_manage(user, complaint) -> bool:
    """Status, priority, assignment and ward: corporators within their ward."""
    if not is_corporator(user):
        return False
    return not user.ward_id or complaint.ward_id in (None, user.ward_id)


def can_comment(user, complaint) -> bool:
    """The conversation is between the reporter and the municipality."""
    return is_owner(user, complaint) or can_manage(user, complaint)


def can_upvote(user, complaint) -> bool:
    """'This affects me too' only means something coming from someone else."""
    return bool(user and user.is_authenticated) and not is_owner(user, complaint)


def can_see_reporter(user, complaint) -> bool:
    """Neighbours browsing the ward feed see the issue, not who reported it."""
    return is_owner(user, complaint) or is_corporator(user)


def actions_for(user, complaint) -> dict:
    """Everything a template needs to decide which controls to render."""
    return {
        'is_owner': is_owner(user, complaint),
        'can_edit': can_edit(user, complaint),
        'can_delete': can_delete(user, complaint),
        'can_manage': can_manage(user, complaint),
        'can_comment': can_comment(user, complaint),
        'can_upvote': can_upvote(user, complaint),
        'can_see_reporter': can_see_reporter(user, complaint),
    }
