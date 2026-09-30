# complaints/admin.py
from django.contrib import admin
from django.db.models import Count
from django.utils.html import format_html

from . import services
from .models import Comment, Complaint, Priority, Status, StatusHistory, Upvote, Ward


class StatusHistoryInline(admin.TabularInline):
    model = StatusHistory
    extra = 0
    can_delete = False
    fields = readonly_fields = ['created_at', 'kind', 'changed_by', 'old_status', 'new_status', 'note']
    ordering = ['-created_at']

    def has_add_permission(self, request, obj=None):
        # The audit trail is written by the service layer, never by hand.
        return False


class CommentInline(admin.TabularInline):
    model = Comment
    extra = 0
    readonly_fields = ['author', 'is_official', 'created_at']
    fields = ['author', 'body', 'is_official', 'created_at']


@admin.register(Ward)
class WardAdmin(admin.ModelAdmin):
    list_display = ['number', 'name', 'city', 'complaint_count']
    search_fields = ['name', 'city']
    list_filter = ['city']

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(n=Count('complaints'))

    @admin.display(description='Complaints', ordering='n')
    def complaint_count(self, obj):
        return obj.n


@admin.register(Complaint)
class ComplaintAdmin(admin.ModelAdmin):
    list_display = ['id', 'headline', 'issue_type', 'status_badge', 'priority', 'ward', 'assigned_to',
                    'user', 'created_at']
    list_filter = ['status', 'priority', 'issue_type', 'ward', ('assigned_to', admin.RelatedOnlyFieldListFilter),
                   'image_processed', 'created_at']
    search_fields = ['id', 'title', 'description', 'address', 'user__username']
    list_per_page = 50
    date_hierarchy = 'created_at'
    ordering = ['-created_at']
    autocomplete_fields = ['ward']
    raw_id_fields = ['user']
    # Workflow fields are read-only here: status moves go through the bulk
    # actions (which call services.change_status), and priority/ward edits are
    # routed through services.update_handling in save_model, so the admin can
    # never change a complaint without writing to the audit trail.
    readonly_fields = ['status', 'resolved_at', 'assigned_to', 'latitude', 'longitude',
                       'created_at', 'updated_at', 'image_processed', 'thumbnail', 'photo_preview']
    inlines = [StatusHistoryInline, CommentInline]
    list_select_related = ['user', 'ward', 'assigned_to']
    actions = ['mark_seen', 'mark_in_progress', 'mark_resolved', 'mark_rejected',
               'set_priority_high', 'set_priority_urgent']

    fieldsets = (
        ('Report', {'fields': ('user', 'issue_type', 'title', 'description')}),
        ('Location', {'fields': ('address', 'ward', 'latitude', 'longitude')}),
        ('Photo', {'fields': ('image', 'photo_preview', 'thumbnail', 'image_processed')}),
        ('Handling', {'fields': ('status', 'priority', 'assigned_to', 'resolved_at')}),
        ('Timestamps', {'fields': ('created_at', 'updated_at'), 'classes': ('collapse',)}),
    )

    @admin.display(description='Status', ordering='status')
    def status_badge(self, obj):
        colors = {
            Status.SUBMITTED: '#9a5b00', Status.SEEN: '#1f5fa8', Status.IN_PROGRESS: '#5b3fb0',
            Status.RESOLVED: '#1e6b43', Status.REJECTED: '#a12a2a',
        }
        return format_html(
            '<span style="background:{};color:#fff;padding:2px 8px;border-radius:10px;font-size:11px">{}</span>',
            colors.get(obj.status, '#4a5568'),
            obj.get_status_display(),
        )

    @admin.display(description='Preview')
    def photo_preview(self, obj):
        target = obj.thumbnail or obj.image
        if not target:
            return '—'
        return format_html('<img src="{}" style="max-height:220px;border-radius:8px">', target.url)

    def save_model(self, request, obj, form, change):
        handled = {f: form.cleaned_data[f] for f in ('priority', 'ward') if change and f in form.changed_data}
        if handled:
            # Save everything else as-is, then apply the audited fields via the service.
            original = Complaint.objects.get(pk=obj.pk)
            for field in handled:
                setattr(obj, field, getattr(original, field))
        super().save_model(request, obj, form, change)
        if handled:
            services.update_handling(obj, actor=request.user, note='Changed in admin.', **handled)

    def _bulk_transition(self, request, queryset, new_status):
        """Route bulk actions through the service so history is still written."""
        changed, skipped = 0, 0
        for complaint in queryset:
            try:
                services.change_status(complaint, new_status=new_status, actor=request.user,
                                       note='Changed from admin bulk action.')
                changed += 1
            except services.TransitionError:
                skipped += 1
        self.message_user(request, f'{changed} updated, {skipped} skipped (transition not allowed).')

    @admin.action(description='Mark selected as Seen')
    def mark_seen(self, request, queryset):
        self._bulk_transition(request, queryset, Status.SEEN)

    @admin.action(description='Mark selected as In Progress')
    def mark_in_progress(self, request, queryset):
        self._bulk_transition(request, queryset, Status.IN_PROGRESS)

    @admin.action(description='Mark selected as Resolved')
    def mark_resolved(self, request, queryset):
        self._bulk_transition(request, queryset, Status.RESOLVED)

    @admin.action(description='Mark selected as Rejected')
    def mark_rejected(self, request, queryset):
        self._bulk_transition(request, queryset, Status.REJECTED)

    def _bulk_priority(self, request, queryset, priority):
        changed = sum(
            1 for complaint in queryset
            if services.update_handling(complaint, actor=request.user, priority=priority,
                                        note='Changed from admin bulk action.')
        )
        self.message_user(request, f'Priority updated on {changed} complaint(s).')

    @admin.action(description='Set priority: High')
    def set_priority_high(self, request, queryset):
        self._bulk_priority(request, queryset, Priority.HIGH)

    @admin.action(description='Set priority: Urgent')
    def set_priority_urgent(self, request, queryset):
        self._bulk_priority(request, queryset, Priority.URGENT)


@admin.register(StatusHistory)
class StatusHistoryAdmin(admin.ModelAdmin):
    list_display = ['complaint', 'kind', 'old_status', 'new_status', 'changed_by', 'note', 'created_at']
    list_filter = ['kind', 'new_status', 'created_at']
    search_fields = ['complaint__id', 'note']
    list_select_related = ['complaint', 'changed_by']

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Comment)
class CommentAdmin(admin.ModelAdmin):
    list_display = ['complaint', 'author', 'is_official', 'created_at']
    list_filter = ['is_official', 'created_at']
    search_fields = ['body', 'author__username']
    list_select_related = ['complaint', 'author']


@admin.register(Upvote)
class UpvoteAdmin(admin.ModelAdmin):
    list_display = ['complaint', 'user', 'created_at']
    list_select_related = ['complaint', 'user']
