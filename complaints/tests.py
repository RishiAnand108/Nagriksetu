# complaints/tests.py
from django.test import Client, TestCase
from django.urls import reverse

from complaints import services
from complaints.models import (
    Comment,
    Complaint,
    Priority,
    Status,
    StatusHistory,
    Upvote,
    Ward,
)
from users.models import CustomUser


def make_user(username, role='citizen', **extra):
    return CustomUser.objects.create_user(
        username=username, password='test1234', role=role, **extra
    )


def make_complaint(user, **overrides):
    defaults = {
        'issue_type': 'garbage',
        'description': 'Bin has not been emptied in a week.',
        'latitude': 18.5204,
        'longitude': 73.8567,
    }
    defaults.update(overrides)
    return Complaint.objects.create(user=user, **defaults)


# ── Model ─────────────────────────────────────────────────
class ComplaintModelTest(TestCase):
    def setUp(self):
        self.user = make_user('testcitizen')
        self.complaint = make_complaint(self.user)

    def test_complaint_created_successfully(self):
        self.assertEqual(Complaint.objects.count(), 1)
        self.assertEqual(self.complaint.issue_type, 'garbage')

    def test_default_status_is_submitted(self):
        self.assertEqual(self.complaint.status, Status.SUBMITTED)

    def test_default_priority_is_normal(self):
        self.assertEqual(self.complaint.priority, Priority.NORMAL)

    def test_str_includes_id_and_labels(self):
        self.assertEqual(str(self.complaint), f'#{self.complaint.pk} Garbage — Submitted')

    def test_ordering_is_newest_first(self):
        newer = make_complaint(self.user, issue_type='road')
        self.assertEqual(Complaint.objects.first(), newer)

    def test_headline_falls_back_to_description_then_issue_type(self):
        self.assertTrue(self.complaint.headline.startswith('Bin has not'))

        titled = make_complaint(self.user, title='Broken streetlight')
        self.assertEqual(titled.headline, 'Broken streetlight')

        bare = make_complaint(self.user, issue_type='water', description='')
        self.assertEqual(bare.headline, 'Water Supply')

    def test_visible_to_scopes_by_role(self):
        other = make_user('other')
        make_complaint(other)
        corporator = make_user('corp', role='corporator')

        self.assertEqual(Complaint.objects.visible_to(self.user).count(), 1)
        self.assertEqual(Complaint.objects.visible_to(corporator).count(), 2)

    def test_upvote_is_unique_per_user(self):
        Upvote.objects.create(complaint=self.complaint, user=self.user)
        with self.assertRaises(Exception):
            Upvote.objects.create(complaint=self.complaint, user=self.user)


# ── Services ──────────────────────────────────────────────
class CoordinateParsingTest(TestCase):
    """Regression coverage for the crash that float(request.POST[...]) caused."""

    def test_empty_string_becomes_zero(self):
        self.assertEqual(services.parse_latitude(''), 0.0)
        self.assertEqual(services.parse_longitude(None), 0.0)

    def test_garbage_becomes_zero(self):
        self.assertEqual(services.parse_latitude('not-a-number'), 0.0)
        self.assertEqual(services.parse_longitude('NaN'), 0.0)

    def test_out_of_range_becomes_zero(self):
        self.assertEqual(services.parse_latitude('91.0'), 0.0)
        self.assertEqual(services.parse_longitude('-181'), 0.0)

    def test_valid_values_pass_through(self):
        self.assertAlmostEqual(services.parse_latitude('18.5204'), 18.5204)
        self.assertAlmostEqual(services.parse_longitude('73.8567'), 73.8567)


class StatusTransitionTest(TestCase):
    def setUp(self):
        self.citizen = make_user('citizen1')
        self.corporator = make_user('corp1', role='corporator')
        self.complaint = make_complaint(self.citizen)

    def test_change_status_records_history(self):
        services.change_status(self.complaint, new_status='seen', actor=self.corporator, note='Site visit booked')
        entry = StatusHistory.objects.get(complaint=self.complaint)
        self.assertEqual(entry.old_status, 'submitted')
        self.assertEqual(entry.new_status, 'seen')
        self.assertEqual(entry.changed_by, self.corporator)
        self.assertEqual(entry.note, 'Site visit booked')

    def test_resolving_sets_resolved_at(self):
        services.change_status(self.complaint, new_status='resolved', actor=self.corporator)
        self.complaint.refresh_from_db()
        self.assertIsNotNone(self.complaint.resolved_at)

    def test_reopening_clears_resolved_at(self):
        services.change_status(self.complaint, new_status='resolved', actor=self.corporator)
        services.change_status(self.complaint, new_status='in_progress', actor=self.corporator)
        self.complaint.refresh_from_db()
        self.assertIsNone(self.complaint.resolved_at)

    def test_first_handler_is_auto_assigned(self):
        services.change_status(self.complaint, new_status='seen', actor=self.corporator)
        self.complaint.refresh_from_db()
        self.assertEqual(self.complaint.assigned_to, self.corporator)

    def test_illegal_transition_is_rejected(self):
        services.change_status(self.complaint, new_status='resolved', actor=self.corporator)
        with self.assertRaises(services.TransitionError):
            services.change_status(self.complaint, new_status='submitted', actor=self.corporator)

    def test_unknown_status_is_rejected(self):
        with self.assertRaises(services.TransitionError):
            services.change_status(self.complaint, new_status='banana', actor=self.corporator)

    def test_no_op_transition_is_rejected(self):
        with self.assertRaises(services.TransitionError):
            services.change_status(self.complaint, new_status='submitted', actor=self.corporator)


class UpvoteServiceTest(TestCase):
    def setUp(self):
        self.user = make_user('voter')
        self.complaint = make_complaint(make_user('author'))

    def test_toggle_adds_then_removes(self):
        upvoted, count = services.toggle_upvote(self.complaint, user=self.user)
        self.assertTrue(upvoted)
        self.assertEqual(count, 1)

        upvoted, count = services.toggle_upvote(self.complaint, user=self.user)
        self.assertFalse(upvoted)
        self.assertEqual(count, 0)


class DashboardStatsTest(TestCase):
    def test_counts_and_resolution_rate(self):
        user = make_user('statuser')
        corporator = make_user('statcorp', role='corporator')
        for _ in range(3):
            make_complaint(user)
        resolved = make_complaint(user)
        services.change_status(resolved, new_status='resolved', actor=corporator)

        stats = services.dashboard_stats()
        self.assertEqual(stats['total'], 4)
        self.assertEqual(stats['submitted'], 3)
        self.assertEqual(stats['resolved'], 1)
        self.assertEqual(stats['open'], 3)
        self.assertEqual(stats['resolution_rate'], 25)

    def test_empty_database_does_not_divide_by_zero(self):
        self.assertEqual(services.dashboard_stats()['resolution_rate'], 0)


class CreateComplaintServiceTest(TestCase):
    def test_creation_seeds_history(self):
        user = make_user('filer')
        complaint = services.create_complaint(
            user=user,
            form_data={'issue_type': 'road', 'description': 'Pothole', 'title': '', 'address': ''},
            latitude=18.5, longitude=73.8,
        )
        entry = complaint.history.get()
        self.assertEqual(entry.old_status, '')
        self.assertEqual(entry.new_status, 'submitted')

    def test_single_ward_is_auto_assigned(self):
        ward = Ward.objects.create(number=7, name='Kothrud')
        complaint = services.create_complaint(
            user=make_user('warduser'),
            form_data={'issue_type': 'water', 'description': 'No supply', 'title': '', 'address': ''},
            latitude=18.5, longitude=73.8,
        )
        self.assertEqual(complaint.ward, ward)

    def test_ambiguous_wards_are_left_unassigned(self):
        Ward.objects.create(number=1, name='A')
        Ward.objects.create(number=2, name='B')
        complaint = services.create_complaint(
            user=make_user('warduser2'),
            form_data={'issue_type': 'water', 'description': 'No supply', 'title': '', 'address': ''},
            latitude=18.5, longitude=73.8,
        )
        self.assertIsNone(complaint.ward)


# ── Web views ─────────────────────────────────────────────
class ComplaintViewTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.citizen = make_user('citizen1')
        self.other = make_user('citizen2')
        self.corporator = make_user('corporator1', role='corporator')
        self.complaint = make_complaint(self.citizen, description='Test complaint')

    def test_list_requires_login(self):
        response = self.client.get(reverse('complaint-list'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('/users/login/', response['Location'])

    def test_citizen_can_see_list(self):
        self.client.force_login(self.citizen)
        self.assertEqual(self.client.get(reverse('complaint-list')).status_code, 200)

    def test_citizen_sees_only_own_complaints(self):
        make_complaint(self.other, issue_type='road')
        self.client.force_login(self.citizen)
        complaints = self.client.get(reverse('complaint-list')).context['complaints']
        self.assertEqual(len(complaints), 1)
        self.assertEqual(complaints[0].user, self.citizen)

    def test_corporator_sees_all_complaints(self):
        make_complaint(self.other, issue_type='road')
        self.client.force_login(self.corporator)
        self.assertEqual(len(self.client.get(reverse('complaint-list')).context['complaints']), 2)

    def test_search_filters_the_list(self):
        make_complaint(self.citizen, title='Streetlight out on MG Road', issue_type='streetlight')
        self.client.force_login(self.citizen)
        results = self.client.get(reverse('complaint-list'), {'q': 'MG Road'}).context['complaints']
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].title, 'Streetlight out on MG Road')

    def test_detail_loads_for_owner(self):
        self.client.force_login(self.citizen)
        response = self.client.get(reverse('complaint-detail', args=[self.complaint.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Test complaint')

    def test_citizen_cannot_read_another_citizens_complaint(self):
        """Regression: the detail view used to query every complaint (IDOR)."""
        self.client.force_login(self.other)
        response = self.client.get(reverse('complaint-detail', args=[self.complaint.pk]))
        self.assertEqual(response.status_code, 404)

    def test_corporator_can_read_any_complaint(self):
        self.client.force_login(self.corporator)
        response = self.client.get(reverse('complaint-detail', args=[self.complaint.pk]))
        self.assertEqual(response.status_code, 200)

    def test_citizen_cannot_access_dashboard(self):
        self.client.force_login(self.citizen)
        self.assertEqual(self.client.get(reverse('corporator-dashboard')).status_code, 403)

    def test_anonymous_dashboard_redirects_with_next(self):
        response = self.client.get(reverse('corporator-dashboard'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('next=', response['Location'])

    def test_corporator_can_access_dashboard(self):
        self.client.force_login(self.corporator)
        self.assertEqual(self.client.get(reverse('corporator-dashboard')).status_code, 200)

    def test_corporator_can_update_status(self):
        self.client.force_login(self.corporator)
        response = self.client.post(reverse('update-status', args=[self.complaint.pk]), {'status': 'seen'})
        self.assertEqual(response.status_code, 302)
        self.complaint.refresh_from_db()
        self.assertEqual(self.complaint.status, 'seen')

    def test_citizen_cannot_update_status(self):
        self.client.force_login(self.citizen)
        response = self.client.post(reverse('update-status', args=[self.complaint.pk]), {'status': 'resolved'})
        self.assertEqual(response.status_code, 403)
        self.complaint.refresh_from_db()
        self.assertEqual(self.complaint.status, 'submitted')

    def test_status_update_rejects_get(self):
        self.client.force_login(self.corporator)
        self.assertEqual(
            self.client.get(reverse('update-status', args=[self.complaint.pk])).status_code, 405
        )

    def test_create_requires_login(self):
        response = self.client.post(reverse('complaint-create'), {'issue_type': 'garbage', 'description': 'x'})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Complaint.objects.count(), 1)

    def test_create_survives_missing_gps(self):
        """Regression: an empty latitude used to raise ValueError inside the view."""
        self.client.force_login(self.citizen)
        response = self.client.post(reverse('complaint-create'), {
            'issue_type': 'water',
            'description': 'No water since morning',
            'latitude': '',
            'longitude': '',
        })
        self.assertEqual(response.status_code, 302)
        created = Complaint.objects.exclude(pk=self.complaint.pk).get()
        self.assertEqual(created.latitude, 0.0)
        self.assertEqual(created.longitude, 0.0)

    def test_create_rejects_empty_report(self):
        self.client.force_login(self.citizen)
        response = self.client.post(reverse('complaint-create'), {'issue_type': 'water', 'description': ''})
        self.assertEqual(response.status_code, 400)
        self.assertContains(response, 'Add a description or a photo', status_code=400)

    def test_comment_can_be_posted_by_owner(self):
        self.client.force_login(self.citizen)
        self.client.post(reverse('complaint-comment', args=[self.complaint.pk]), {'body': 'Any update?'})
        self.assertEqual(Comment.objects.count(), 1)

    def test_corporator_comment_is_marked_official(self):
        self.client.force_login(self.corporator)
        self.client.post(reverse('complaint-comment', args=[self.complaint.pk]), {'body': 'Crew dispatched.'})
        self.assertTrue(Comment.objects.get().is_official)

    def test_stranger_cannot_comment_on_private_complaint(self):
        self.client.force_login(self.other)
        response = self.client.post(reverse('complaint-comment', args=[self.complaint.pk]), {'body': 'hi'})
        self.assertEqual(response.status_code, 404)
        self.assertEqual(Comment.objects.count(), 0)

    def test_upvote_toggles_over_ajax(self):
        # Neighbours in the same ward can see (and support) each other's reports.
        ward = Ward.objects.create(number=1, name='Kothrud')
        CustomUser.objects.filter(pk__in=[self.citizen.pk, self.other.pk]).update(ward=ward)
        Complaint.objects.filter(pk=self.complaint.pk).update(ward=ward)
        self.other.refresh_from_db()
        self.client.force_login(self.other)
        url = reverse('complaint-upvote', args=[self.complaint.pk])
        response = self.client.post(url, headers={'x-requested-with': 'XMLHttpRequest'})
        self.assertEqual(response.json(), {'upvoted': True, 'count': 1})

        response = self.client.post(url, headers={'x-requested-with': 'XMLHttpRequest'})
        self.assertEqual(response.json(), {'upvoted': False, 'count': 0})

    def test_cannot_upvote_a_complaint_outside_your_visibility(self):
        # Regression: the web endpoint once skipped visible_to() and leaked vote counts.
        self.client.force_login(self.other)
        url = reverse('complaint-upvote', args=[self.complaint.pk])
        response = self.client.post(url, headers={'x-requested-with': 'XMLHttpRequest'})
        self.assertEqual(response.status_code, 404)
        self.assertFalse(Upvote.objects.exists())

    def test_map_data_excludes_complaints_without_coordinates(self):
        make_complaint(self.citizen, latitude=0.0, longitude=0.0)
        self.client.force_login(self.citizen)
        payload = self.client.get(reverse('complaint-map-data')).json()
        self.assertEqual(payload['count'], 1)

    def test_map_data_requires_login(self):
        self.assertEqual(self.client.get(reverse('complaint-map-data')).status_code, 403)


# ── REST API ──────────────────────────────────────────────
class ComplaintAPITest(TestCase):
    def setUp(self):
        self.client = Client()
        self.citizen = make_user('apicitizen')
        self.other = make_user('apiother')
        self.corporator = make_user('apicorp', role='corporator')
        self.complaint = make_complaint(self.citizen, issue_type='water', description='No water supply')

    def test_requires_authentication(self):
        response = self.client.get('/api/complaints/')
        self.assertIn(response.status_code, (401, 403))

    def test_returns_json(self):
        self.client.force_login(self.citizen)
        response = self.client.get('/api/complaints/', headers={'accept': 'application/json'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')

    def test_list_is_paginated_and_scoped(self):
        make_complaint(self.other)
        self.client.force_login(self.citizen)
        data = self.client.get('/api/complaints/', headers={'accept': 'application/json'}).json()
        self.assertEqual(data['count'], 1)
        self.assertEqual(data['results'][0]['description'], 'No water supply')

    def test_corporator_sees_everything(self):
        make_complaint(self.other)
        self.client.force_login(self.corporator)
        data = self.client.get('/api/complaints/', headers={'accept': 'application/json'}).json()
        self.assertEqual(data['count'], 2)

    def test_detail_is_not_readable_by_a_stranger(self):
        """Regression: ComplaintDetailAPI used to fetch by pk with no scoping."""
        self.client.force_login(self.other)
        response = self.client.get(f'/api/complaints/{self.complaint.pk}/', headers={'accept': 'application/json'})
        self.assertEqual(response.status_code, 404)

    def test_filter_by_issue_type(self):
        make_complaint(self.citizen, issue_type='road')
        self.client.force_login(self.citizen)
        data = self.client.get('/api/complaints/?issue_type=road', headers={'accept': 'application/json'}).json()
        self.assertEqual(data['count'], 1)

    def test_search(self):
        make_complaint(self.citizen, title='Pothole near school', issue_type='road')
        self.client.force_login(self.citizen)
        data = self.client.get('/api/complaints/?search=pothole', headers={'accept': 'application/json'}).json()
        self.assertEqual(data['count'], 1)

    def test_create_ignores_client_supplied_status(self):
        self.client.force_login(self.citizen)
        response = self.client.post(
            '/api/complaints/',
            {'issue_type': 'garbage', 'description': 'Overflowing bin', 'status': 'resolved'},
            headers={'accept': 'application/json'},
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(Complaint.objects.get(description='Overflowing bin').status, 'submitted')

    def test_status_action_requires_corporator(self):
        self.client.force_login(self.citizen)
        response = self.client.post(
            f'/api/complaints/{self.complaint.pk}/status/',
            {'status': 'resolved'},
            content_type='application/json',
            headers={'accept': 'application/json'},
        )
        self.assertEqual(response.status_code, 403)

    def test_status_action_updates_and_records_history(self):
        self.client.force_login(self.corporator)
        response = self.client.post(
            f'/api/complaints/{self.complaint.pk}/status/',
            {'status': 'seen', 'note': 'Logged'},
            content_type='application/json',
            headers={'accept': 'application/json'},
        )
        self.assertEqual(response.status_code, 200)
        self.complaint.refresh_from_db()
        self.assertEqual(self.complaint.status, 'seen')
        self.assertEqual(self.complaint.history.count(), 1)

    def test_status_action_rejects_illegal_transition(self):
        services.change_status(self.complaint, new_status='resolved', actor=self.corporator)
        self.client.force_login(self.corporator)
        response = self.client.post(
            f'/api/complaints/{self.complaint.pk}/status/',
            {'status': 'submitted'},
            content_type='application/json',
            headers={'accept': 'application/json'},
        )
        self.assertEqual(response.status_code, 400)

    def test_upvote_action(self):
        self.client.force_login(self.corporator)
        response = self.client.post(
            f'/api/complaints/{self.complaint.pk}/upvote/', headers={'accept': 'application/json'}
        )
        self.assertEqual(response.json(), {'upvoted': True, 'count': 1})

    def test_stats_action(self):
        self.client.force_login(self.citizen)
        data = self.client.get('/api/complaints/stats/', headers={'accept': 'application/json'}).json()
        self.assertEqual(data['total'], 1)
        self.assertEqual(data['submitted'], 1)

    def test_citizen_cannot_edit_a_complaint_in_progress(self):
        services.change_status(self.complaint, new_status='in_progress', actor=self.corporator)
        self.client.force_login(self.citizen)
        response = self.client.patch(
            f'/api/complaints/{self.complaint.pk}/',
            {'description': 'edited'},
            content_type='application/json',
            headers={'accept': 'application/json'},
        )
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()['code'], 'conflict')

    def test_owner_can_patch_a_single_field(self):
        # Regression: partial updates were validated as if every field were missing.
        self.client.force_login(self.citizen)
        response = self.client.patch(
            f'/api/complaints/{self.complaint.pk}/',
            {'title': 'Updated title'},
            content_type='application/json',
            headers={'accept': 'application/json'},
        )
        self.assertEqual(response.status_code, 200)
        self.complaint.refresh_from_db()
        self.assertEqual(self.complaint.title, 'Updated title')

    def test_schema_endpoint_is_served(self):
        self.client.force_login(self.citizen)
        self.assertEqual(self.client.get('/api/schema/').status_code, 200)
