# complaints/forms.py
from django import forms

from users.models import CustomUser

from . import rules
from .models import Comment, Complaint, IssueType, Priority, Status, Ward


class ComplaintForm(forms.ModelForm):
    """
    Citizen-facing complaint form, used for filing and for editing.

    latitude/longitude stay out of the form: they are filled by the GPS script
    and parsed in complaints.services, so a spoofed or missing coordinate can
    never raise inside the view.
    """

    class Meta:
        model = Complaint
        fields = ['issue_type', 'title', 'description', 'address', 'image']
        widgets = {
            'issue_type': forms.RadioSelect,
            'title': forms.TextInput(attrs={
                'class': 'field-input',
                'placeholder': 'e.g. Overflowing bin near the bus stop',
                'maxlength': 120,
            }),
            'description': forms.Textarea(attrs={
                'class': 'field-input',
                'rows': 4,
                'maxlength': 2000,
                'placeholder': 'What is wrong, and how long has it been like this?',
            }),
            'address': forms.TextInput(attrs={
                'class': 'field-input',
                'placeholder': 'Nearby landmark or street name',
            }),
            'image': forms.FileInput(attrs={
                'class': 'visually-hidden',
                'accept': 'image/jpeg,image/png,image/webp',
            }),
        }
        labels = {
            'issue_type': 'What kind of issue is it?',
            'title': 'Short title',
            'description': 'Description',
            'address': 'Landmark / address',
            'image': 'Photo',
        }
        help_texts = {
            'address': 'Helps the ward office find the spot, especially if location is unavailable.',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Radio cards: no blank "---------" option.
        self.fields['issue_type'].choices = IssueType.choices

    def clean_image(self):
        image = self.cleaned_data.get('image')
        rules.validate_photo(image)
        return image

    def clean(self):
        cleaned = super().clean()
        rules.require_description_or_photo(cleaned.get('description'), cleaned.get('image'))
        return cleaned


class CommentForm(forms.ModelForm):
    class Meta:
        model = Comment
        fields = ['body']
        widgets = {
            'body': forms.Textarea(attrs={
                'class': 'field-input',
                'rows': 3,
                'maxlength': 1000,
                'placeholder': 'Add an update or ask a question…',
            }),
        }
        labels = {'body': 'Your message'}

    def clean_body(self):
        body = (self.cleaned_data.get('body') or '').strip()
        if not body:
            raise forms.ValidationError('Comment cannot be empty.')
        return body


class StatusUpdateForm(forms.Form):
    """Corporator status change, with an optional note for the audit trail."""

    status = forms.ChoiceField(choices=Status.choices, widget=forms.Select(attrs={'class': 'field-input'}))
    note = forms.CharField(
        max_length=255, required=False,
        widget=forms.TextInput(attrs={'class': 'field-input', 'placeholder': 'Visible to the citizen in the timeline'}),
    )

    def __init__(self, *args, complaint=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.complaint = complaint
        if complaint is not None:
            self.fields['status'].choices = complaint.allowed_next_choices()


class HandlingForm(forms.Form):
    """Priority, assignee and ward — the triage controls for corporators."""

    priority = forms.TypedChoiceField(
        choices=Priority.choices, coerce=int,
        widget=forms.Select(attrs={'class': 'field-input'}),
    )
    assigned_to = forms.ModelChoiceField(
        queryset=CustomUser.objects.none(), required=False, empty_label='Unassigned',
        widget=forms.Select(attrs={'class': 'field-input'}),
    )
    ward = forms.ModelChoiceField(
        queryset=Ward.objects.all(), required=False, empty_label='Not routed to a ward',
        widget=forms.Select(attrs={'class': 'field-input'}),
    )
    note = forms.CharField(
        max_length=200, required=False,
        widget=forms.TextInput(attrs={'class': 'field-input', 'placeholder': 'Optional reason'}),
    )

    def __init__(self, *args, complaint, assignees, **kwargs):
        kwargs.setdefault('initial', {
            'priority': complaint.priority,
            'assigned_to': complaint.assigned_to_id,
            'ward': complaint.ward_id,
        })
        super().__init__(*args, **kwargs)
        self.fields['assigned_to'].queryset = assignees
        self.fields['assigned_to'].label_from_instance = (
            lambda u: f'{u.display_name} ({u.ward.name if u.ward_id else "City-wide"})'
        )


class ComplaintFilterForm(forms.Form):
    """Search and filter controls shared by the lists, dashboard and map."""

    SCOPE_CHOICES = [('mine', 'My reports'), ('ward', 'My ward')]
    ASSIGNED_CHOICES = [('', 'Anyone'), ('me', 'Assigned to me'), ('none', 'Unassigned')]
    ORDERING_CHOICES = [
        ('-created_at', 'Newest first'),
        ('created_at', 'Oldest first'),
        ('-priority', 'Highest priority'),
        ('-upvote_count', 'Most upvoted'),
        ('-updated_at', 'Recently updated'),
    ]

    q = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'field-input',
            'placeholder': 'Title, description, landmark or #ID',
            'type': 'search',
        }),
    )
    scope = forms.ChoiceField(required=False, choices=SCOPE_CHOICES, widget=forms.HiddenInput)
    status = forms.ChoiceField(
        required=False,
        choices=[('', 'Any status'), ('open', 'All open')] + list(Status.choices),
        widget=forms.Select(attrs={'class': 'field-input'}),
    )
    issue_type = forms.ChoiceField(
        required=False,
        choices=[('', 'Any issue')] + list(IssueType.choices),
        widget=forms.Select(attrs={'class': 'field-input'}),
    )
    priority = forms.TypedChoiceField(
        required=False, coerce=int, empty_value=None,
        choices=[('', 'Any priority')] + list(Priority.choices),
        widget=forms.Select(attrs={'class': 'field-input'}),
    )
    ward = forms.ModelChoiceField(
        required=False,
        queryset=Ward.objects.all(),
        empty_label='Any ward',
        widget=forms.Select(attrs={'class': 'field-input'}),
    )
    assigned = forms.ChoiceField(
        required=False, choices=ASSIGNED_CHOICES,
        widget=forms.Select(attrs={'class': 'field-input'}),
    )
    ordering = forms.ChoiceField(
        required=False,
        choices=ORDERING_CHOICES,
        widget=forms.Select(attrs={'class': 'field-input'}),
    )

    ACTIVE_KEYS = ('q', 'status', 'issue_type', 'priority', 'ward', 'assigned')
