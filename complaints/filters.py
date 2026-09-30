# complaints/filters.py
import django_filters as filters

from .models import CLOSED_STATUSES, Complaint, IssueType, Priority, Status, Ward


class ComplaintFilter(filters.FilterSet):
    """Query-string filters for the complaints API."""

    status = filters.MultipleChoiceFilter(choices=Status.choices)
    issue_type = filters.MultipleChoiceFilter(choices=IssueType.choices)
    priority = filters.MultipleChoiceFilter(choices=Priority.choices)
    ward = filters.ModelChoiceFilter(queryset=Ward.objects.all())
    is_open = filters.BooleanFilter(method='filter_is_open', label='Only unresolved complaints')
    created_after = filters.DateTimeFilter(field_name='created_at', lookup_expr='gte')
    created_before = filters.DateTimeFilter(field_name='created_at', lookup_expr='lte')
    mine = filters.BooleanFilter(method='filter_mine', label='Only complaints I reported')
    assigned_to_me = filters.BooleanFilter(method='filter_assigned_to_me', label='Only complaints assigned to me')

    class Meta:
        model = Complaint
        fields = ['status', 'issue_type', 'priority', 'ward']

    def filter_is_open(self, queryset, name, value):
        if value is None:
            return queryset
        return queryset.exclude(status__in=CLOSED_STATUSES) if value else queryset.filter(status__in=CLOSED_STATUSES)

    def _user_filter(self, queryset, value, field):
        if not value:
            return queryset
        user = getattr(self.request, 'user', None)
        return queryset.filter(**{field: user}) if user and user.is_authenticated else queryset.none()

    def filter_mine(self, queryset, name, value):
        return self._user_filter(queryset, value, 'user')

    def filter_assigned_to_me(self, queryset, name, value):
        return self._user_filter(queryset, value, 'assigned_to')
