# complaints/views.py
"""HTML views. The REST API lives in complaints/api.py; both share services and policies."""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.http import require_POST
from django.views.generic import DetailView, ListView

from core.http import is_ajax, safe_next
from core.ratelimit import filing_throttled

from . import policies, services
from .decorators import corporator_required
from .forms import CommentForm, ComplaintFilterForm, ComplaintForm, HandlingForm, StatusUpdateForm
from .models import CLOSED_STATUSES, Complaint, IssueType, Status

ALLOWED_ORDERING = {value for value, _ in ComplaintFilterForm.ORDERING_CHOICES}


def _visible(request):
    return Complaint.objects.visible_to(request.user)


def _apply_filters(queryset, form, user):
    """
    Apply a ComplaintFilterForm to a queryset built with annotated_for().

    Invalid input is ignored field by field rather than failing the page.
    """
    form.is_valid()
    data = getattr(form, 'cleaned_data', {})

    term = (data.get('q') or '').strip()
    if term:
        text = Q(title__icontains=term) | Q(description__icontains=term) | Q(address__icontains=term)
        if term.lstrip('#').isdigit():
            text |= Q(pk=int(term.lstrip('#')))
        queryset = queryset.filter(text)

    status = data.get('status')
    if status == 'open':
        queryset = queryset.exclude(status__in=CLOSED_STATUSES)
    elif status:
        queryset = queryset.filter(status=status)
    if data.get('issue_type'):
        queryset = queryset.filter(issue_type=data['issue_type'])
    if data.get('priority'):
        queryset = queryset.filter(priority=data['priority'])
    if data.get('ward'):
        queryset = queryset.filter(ward=data['ward'])
    if data.get('assigned') == 'me':
        queryset = queryset.filter(assigned_to=user)
    elif data.get('assigned') == 'none':
        queryset = queryset.filter(assigned_to__isnull=True)

    ordering = data.get('ordering')
    ordering = ordering if ordering in ALLOWED_ORDERING else '-created_at'
    return queryset.order_by(ordering, '-pk')


def _has_filters(request):
    return any(request.GET.get(key) for key in ComplaintFilterForm.ACTIVE_KEYS)


# ── Public landing page ───────────────────────────────────
def home(request):
    if request.user.is_authenticated:
        return redirect('dashboard')

    totals = Complaint.objects.aggregate(
        total=Count('id'),
        resolved=Count('id', filter=Q(status=Status.RESOLVED)),
        wards=Count('ward', distinct=True),
    )
    return render(request, 'home.html', {
        'totals': totals,
        'issue_types': IssueType.choices,
    })


# ── Citizen dashboard ─────────────────────────────────────
@login_required
def dashboard(request):
    if policies.is_corporator(request.user):
        return redirect('corporator-dashboard')

    user = request.user
    own = Complaint.objects.filter(user=user)
    ward_feed = []
    if user.ward_id:
        ward_feed = (
            Complaint.objects.filter(ward_id=user.ward_id).exclude(user=user).open()
            .annotated_for(user).order_by('-upvote_count', '-created_at')[:4]
        )

    return render(request, 'complaints/citizen_dashboard.html', {
        'stats': services.dashboard_stats(own),
        'recent': own.annotated_for(user).order_by('-created_at')[:6],
        'ward_feed': ward_feed,
    })


# ── Complaint list ────────────────────────────────────────
class ComplaintListView(LoginRequiredMixin, ListView):
    template_name = 'complaints/complaint_list.html'
    context_object_name = 'complaints'
    paginate_by = 12

    def get_scope(self):
        user = self.request.user
        if policies.is_corporator(user):
            return 'all'
        scope = self.request.GET.get('scope')
        return 'ward' if scope == 'ward' and user.ward_id else 'mine'

    def get_queryset(self):
        user = self.request.user
        self.scope = self.get_scope()
        self.filter_form = ComplaintFilterForm(self.request.GET)
        base = _visible(self.request)
        if self.scope == 'mine':
            base = base.filter(user=user)
        elif self.scope == 'ward':
            base = base.filter(ward_id=user.ward_id)
        return _apply_filters(base.annotated_for(user), self.filter_form, user)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({
            'filter_form': self.filter_form,
            'scope': self.scope,
            'has_filters': _has_filters(self.request),
        })
        return context


# ── Complaint detail ──────────────────────────────────────
class ComplaintDetailView(LoginRequiredMixin, DetailView):
    template_name = 'complaints/complaint_detail.html'
    context_object_name = 'complaint'

    def get_queryset(self):
        # visible_to() is the IDOR fix: an out-of-scope complaint is a 404.
        return _visible(self.request).annotated_for(self.request.user).with_detail()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        complaint, user = self.object, self.request.user
        actions = policies.actions_for(user, complaint)
        history = list(complaint.history.all())
        context.update(actions)
        context.update({
            'comments': complaint.comments.all(),
            'history': history,
            'lifecycle': _lifecycle(complaint, history),
            'comment_form': CommentForm(),
        })
        if actions['can_manage']:
            context['status_form'] = StatusUpdateForm(complaint=complaint)
            context['handling_form'] = HandlingForm(
                complaint=complaint, assignees=services.assignable_corporators(complaint),
            )
        return context


def _lifecycle(complaint, history):
    """
    The four-step progress track shown at the top of the timeline.

    Each step knows whether it has been reached and when it was first reached.
    The last step is Resolved or Rejected depending on how the complaint ended.
    """
    reached_at = {}
    for event in reversed(history):  # history is newest-first
        if event.is_status_change and event.new_status not in reached_at:
            reached_at[event.new_status] = event.created_at
    reached_at.setdefault(Status.SUBMITTED, complaint.created_at)

    final = Status.REJECTED if complaint.status == Status.REJECTED else Status.RESOLVED
    order = [Status.SUBMITTED, Status.SEEN, Status.IN_PROGRESS, final]
    current_index = order.index(complaint.status) if complaint.status in order else 0

    steps = []
    for index, status in enumerate(order):
        passed = index < current_index
        steps.append({
            'key': status.value,
            'label': status.label,
            # Officials may jump straight to a later status; earlier steps
            # that never happened are shown as skipped, not as completed.
            'skipped': passed and status not in reached_at,
            'done': (passed and status in reached_at)
                    or (index == current_index and complaint.status in CLOSED_STATUSES),
            'current': index == current_index,
            'at': reached_at.get(status) if index <= current_index else None,
        })
    return steps


# ── File / edit / delete ──────────────────────────────────
@method_decorator(filing_throttled, name='post')
class ComplaintCreateView(LoginRequiredMixin, View):
    template_name = 'complaints/complaint_form.html'

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated and policies.is_corporator(request.user):
            messages.info(request, 'Complaints are filed by citizens. Corporators manage them from the dashboard.')
            return redirect('corporator-dashboard')
        return super().dispatch(request, *args, **kwargs)

    def get(self, request):
        return render(request, self.template_name, {'form': ComplaintForm(), 'mode': 'create'})

    def post(self, request):
        form = ComplaintForm(request.POST, request.FILES)
        if not form.is_valid():
            return render(request, self.template_name, {'form': form, 'mode': 'create'}, status=400)

        complaint = services.create_complaint(
            user=request.user,
            form_data=form.cleaned_data,
            # parse_* never raises — a denied GPS prompt posts '' and simply
            # yields a complaint with no coordinates.
            latitude=services.parse_latitude(request.POST.get('latitude')),
            longitude=services.parse_longitude(request.POST.get('longitude')),
            image=form.cleaned_data.get('image'),
        )
        messages.success(request, f'Complaint #{complaint.pk} filed. We will keep you posted as it moves.')
        return redirect(complaint.get_absolute_url())


class ComplaintEditView(LoginRequiredMixin, View):
    template_name = 'complaints/complaint_form.html'

    def get_complaint(self, request, pk):
        complaint = get_object_or_404(_visible(request), pk=pk)
        if not policies.can_edit(request.user, complaint):
            raise PermissionDenied('Only the reporter can edit a complaint, and only before work starts.')
        return complaint

    def get(self, request, pk):
        complaint = self.get_complaint(request, pk)
        return render(request, self.template_name, {
            'form': ComplaintForm(instance=complaint), 'mode': 'edit', 'complaint': complaint,
        })

    def post(self, request, pk):
        complaint = self.get_complaint(request, pk)
        form = ComplaintForm(request.POST, request.FILES, instance=complaint)
        if not form.is_valid():
            return render(request, self.template_name, {
                'form': form, 'mode': 'edit', 'complaint': complaint,
            }, status=400)

        changes = {field: form.cleaned_data[field] for field in form.changed_data}
        if request.POST.get('latitude'):
            changes['latitude'] = request.POST['latitude']
            changes['longitude'] = request.POST.get('longitude')
        services.update_complaint(complaint, changes=changes)
        messages.success(request, 'Your complaint has been updated.')
        return redirect(complaint.get_absolute_url())


@login_required
@require_POST
def delete_complaint(request, pk):
    complaint = get_object_or_404(_visible(request), pk=pk)
    if not policies.can_delete(request.user, complaint):
        raise PermissionDenied('Only the reporter can withdraw a complaint, and only before work starts.')
    services.delete_complaint(complaint)
    messages.success(request, f'Complaint #{pk} has been withdrawn.')
    return redirect('complaint-list')


# ── Conversation & upvotes ────────────────────────────────
@require_POST
def add_comment(request, pk):
    if not request.user.is_authenticated:
        raise PermissionDenied
    complaint = get_object_or_404(_visible(request), pk=pk)
    if not policies.can_comment(request.user, complaint):
        raise PermissionDenied('Only the reporter and the ward office can post here.')

    form = CommentForm(request.POST)
    if form.is_valid():
        services.add_comment(complaint, author=request.user, body=form.cleaned_data['body'])
        messages.success(request, 'Your message was posted.')
    else:
        messages.error(request, form.errors.get('body', ['Comment cannot be empty.'])[0])
    return redirect(f'{complaint.get_absolute_url()}#discussion')


@require_POST
def toggle_upvote(request, pk):
    if not request.user.is_authenticated:
        raise PermissionDenied
    # Same visibility rule as every other entry point: no voting on (or
    # probing the vote count of) complaints you cannot see.
    complaint = get_object_or_404(_visible(request), pk=pk)
    if not policies.can_upvote(request.user, complaint):
        if is_ajax(request):
            return JsonResponse({'detail': 'You cannot upvote your own complaint.'}, status=403)
        raise PermissionDenied('You cannot upvote your own complaint.')

    upvoted, total = services.toggle_upvote(complaint, user=request.user)
    if is_ajax(request):
        return JsonResponse({'upvoted': upvoted, 'count': total})
    return redirect(safe_next(request, complaint.get_absolute_url()))


# ── Corporator operations dashboard ───────────────────────
@corporator_required
def corporator_dashboard(request):
    user = request.user
    filter_form = ComplaintFilterForm(request.GET)
    scope = _visible(request)
    complaints = _apply_filters(scope.annotated_for(user), filter_form, user)

    stats_scope = scope
    if filter_form.is_valid() and filter_form.cleaned_data.get('ward'):
        stats_scope = stats_scope.filter(ward=filter_form.cleaned_data['ward'])

    page = Paginator(complaints, 20).get_page(request.GET.get('page'))
    return render(request, 'complaints/corporator_dashboard.html', {
        'page_obj': page,
        'complaints': page.object_list,
        'is_paginated': page.has_other_pages(),
        'filter_form': filter_form,
        'has_filters': _has_filters(request),
        'stats': services.dashboard_stats(stats_scope),
        'my_queue': scope.open().filter(assigned_to=user).count(),
        'breakdown': services.issue_type_breakdown(stats_scope),
        'activity': services.recent_activity(scope, limit=8),
        'ward_scope': user.ward,
    })


@corporator_required
@require_POST
def update_status(request, pk):
    complaint = get_object_or_404(_visible(request), pk=pk)
    if not policies.can_manage(request.user, complaint):
        raise PermissionDenied
    form = StatusUpdateForm(request.POST, complaint=complaint)

    if not form.is_valid():
        messages.error(request, 'That status change is not allowed from the current state.')
    else:
        try:
            services.change_status(
                complaint,
                new_status=form.cleaned_data['status'],
                actor=request.user,
                note=form.cleaned_data.get('note', ''),
            )
            messages.success(request, f'Complaint #{complaint.pk} is now {complaint.get_status_display()}.')
        except services.TransitionError as exc:
            messages.error(request, str(exc))

    return redirect(safe_next(request, reverse('corporator-dashboard')))


@corporator_required
@require_POST
def update_handling(request, pk):
    complaint = get_object_or_404(_visible(request), pk=pk)
    if not policies.can_manage(request.user, complaint):
        raise PermissionDenied
    form = HandlingForm(request.POST, complaint=complaint, assignees=services.assignable_corporators(complaint))

    if not form.is_valid():
        messages.error(request, 'Please check the triage fields and try again.')
    else:
        data = form.cleaned_data
        # Only what the official actually touched — the form posts every field.
        edits = {f: data[f] for f in ('priority', 'assigned_to', 'ward') if f in form.changed_data}
        try:
            changed = services.update_handling(complaint, actor=request.user, note=data.get('note', ''), **edits)
            if changed:
                messages.success(request, 'Saved: ' + '; '.join(changed) + '.')
            else:
                messages.info(request, 'Nothing changed.')
        except services.HandlingError as exc:
            messages.error(request, str(exc))

    return redirect(safe_next(request, complaint.get_absolute_url()))


# ── Map ───────────────────────────────────────────────────
class ComplaintMapView(LoginRequiredMixin, View):
    """Complaints plotted on a map — the point of collecting GPS."""

    def get(self, request):
        return render(request, 'complaints/complaint_map.html', {
            'filter_form': ComplaintFilterForm(request.GET),
            'has_filters': _has_filters(request),
        })


def map_data(request):
    """JSON feed for the map. Same visibility, filters and ordering as the lists."""
    if not request.user.is_authenticated:
        return JsonResponse({'detail': 'Authentication required.'}, status=403)

    form = ComplaintFilterForm(request.GET)
    queryset = _apply_filters(_visible(request).annotated_for(request.user), form, request.user)
    queryset = (
        queryset.exclude(latitude=0.0, longitude=0.0)
        .filter(latitude__gte=-90, latitude__lte=90, longitude__gte=-180, longitude__lte=180)
    )[:500]

    features = [
        {
            'id': c.pk,
            'lat': c.latitude,
            'lng': c.longitude,
            'title': c.headline,
            'issue': c.get_issue_type_display(),
            'issue_key': c.issue_type,
            'status': c.status,
            'status_label': c.get_status_display(),
            'priority': c.get_priority_display(),
            'high_priority': c.is_high_priority,
            'upvotes': c.upvote_count,
            'ward': str(c.ward) if c.ward_id else '',
            'address': c.address,
            'url': c.get_absolute_url(),
            'thumb': c.thumbnail.url if c.thumbnail else '',
            'created': c.created_at.strftime('%d %b %Y'),
        }
        for c in queryset
    ]
    return JsonResponse({'count': len(features), 'complaints': features})
