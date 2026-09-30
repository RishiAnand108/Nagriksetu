# core/permissions.py
"""DRF permission classes. The rules themselves live in complaints.policies."""
from rest_framework.permissions import SAFE_METHODS, BasePermission

from complaints import policies


class IsCorporator(BasePermission):
    """Only municipal corporators may pass."""

    message = 'Only corporators can perform this action.'

    def has_permission(self, request, view):
        return policies.is_corporator(request.user)


class ComplaintAccess(BasePermission):
    """
    Object-level rules for a complaint the caller can already see.

    Visibility is enforced by the queryset (ComplaintQuerySet.visible_to), so an
    out-of-scope complaint 404s before reaching here. This class decides which
    actions on a visible complaint belong to the caller.
    """

    message = 'You do not have permission to perform this action on this complaint.'

    def has_object_permission(self, request, view, obj):
        user, action = request.user, getattr(view, 'action', None)

        if action == 'upvote':
            return policies.can_upvote(user, obj)
        if action == 'comments':
            return request.method in SAFE_METHODS or policies.can_comment(user, obj)
        if action in ('status', 'handling'):
            return policies.can_manage(user, obj)
        if request.method in SAFE_METHODS:
            return True
        # update / partial_update / destroy: the reporter (the service rejects
        # edits once work has started) or a corporator responsible for it.
        return policies.is_owner(user, obj) or policies.can_manage(user, obj)
