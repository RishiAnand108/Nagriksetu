# complaints/tests.py
from django.test import TestCase, Client
from django.urls import reverse
from users.models import CustomUser
from .models import Complaint


class ComplaintModelTest(TestCase):
    """Tests for the Complaint model"""

    def setUp(self):
        # runs before every test — creates fresh test data
        self.user = CustomUser.objects.create_user(
            username='testcitizen',
            password='test1234',
            role='citizen'
        )
        self.complaint = Complaint.objects.create(
            user=self.user,
            issue_type='garbage',
            description='Test garbage complaint',
            latitude=18.5204,
            longitude=73.8567,
        )

    def test_complaint_created_successfully(self):
        """Complaint saves to database correctly"""
        self.assertEqual(Complaint.objects.count(), 1)
        self.assertEqual(self.complaint.issue_type, 'garbage')

    def test_complaint_default_status_is_submitted(self):
        """New complaints should always start as submitted"""
        self.assertEqual(self.complaint.status, 'submitted')

    def test_complaint_str(self):
        """__str__ returns correct format"""
        self.assertEqual(
            str(self.complaint),
            'garbage — submitted'
        )

    def test_complaint_ordering(self):
        """Complaints should be ordered newest first"""
        complaint2 = Complaint.objects.create(
            user=self.user,
            issue_type='road',
            description='Road damage',
            latitude=18.5204,
            longitude=73.8567,
        )
        complaints = Complaint.objects.all()
        # newest (complaint2) should be first
        self.assertEqual(complaints[0], complaint2)


class ComplaintViewTest(TestCase):
    """Tests for complaint views"""

    def setUp(self):
        self.client = Client()

        # create citizen
        self.citizen = CustomUser.objects.create_user(
            username='citizen1',
            password='test1234',
            role='citizen'
        )

        # create corporator
        self.corporator = CustomUser.objects.create_user(
            username='corporator1',
            password='test1234',
            role='corporator'
        )

        # create a complaint
        self.complaint = Complaint.objects.create(
            user=self.citizen,
            issue_type='garbage',
            description='Test complaint',
            latitude=18.5204,
            longitude=73.8567,
        )

    def test_complaint_list_requires_login(self):
        """Unauthenticated users should be redirected to login"""
        response = self.client.get(reverse('complaint-list'))
        # should redirect to login, not show the list
        self.assertNotEqual(response.status_code, 200)

    def test_citizen_can_see_complaint_list(self):
        """Logged in citizen can access complaint list"""
        self.client.login(username='citizen1', password='test1234')
        response = self.client.get(reverse('complaint-list'))
        self.assertEqual(response.status_code, 200)

    def test_citizen_sees_only_own_complaints(self):
        """Citizen should only see their own complaints"""
        # create another citizen with their own complaint
        other_citizen = CustomUser.objects.create_user(
            username='citizen2',
            password='test1234',
            role='citizen'
        )
        Complaint.objects.create(
            user=other_citizen,
            issue_type='road',
            description='Other complaint',
            latitude=18.5204,
            longitude=73.8567,
        )

        self.client.login(username='citizen1', password='test1234')
        response = self.client.get(reverse('complaint-list'))
        complaints = response.context['complaints']

        # citizen1 should see only 1 complaint — their own
        self.assertEqual(complaints.count(), 1)
        self.assertEqual(complaints[0].user, self.citizen)

    def test_complaint_detail_loads(self):
        """Detail page loads for a valid complaint"""
        self.client.login(username='citizen1', password='test1234')
        response = self.client.get(
            reverse('complaint-detail', args=[self.complaint.pk])
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Test complaint')

    def test_citizen_cannot_access_dashboard(self):
        """Citizens must get 403 when accessing corporator dashboard"""
        self.client.login(username='citizen1', password='test1234')
        response = self.client.get(reverse('corporator-dashboard'))
        self.assertEqual(response.status_code, 403)

    def test_corporator_can_access_dashboard(self):
        """Corporator can access the dashboard"""
        self.client.login(username='corporator1', password='test1234')
        response = self.client.get(reverse('corporator-dashboard'))
        self.assertEqual(response.status_code, 200)

    def test_corporator_can_update_status(self):
        """Corporator can change complaint status"""
        self.client.login(username='corporator1', password='test1234')
        response = self.client.post(
            reverse('update-status', args=[self.complaint.pk]),
            {'status': 'seen'}
        )
        # should redirect after update
        self.assertEqual(response.status_code, 302)

        # refresh from database
        self.complaint.refresh_from_db()
        self.assertEqual(self.complaint.status, 'seen')

    def test_complaint_create_requires_login(self):
        """Unauthenticated users cannot create complaints"""
        response = self.client.post(reverse('complaint-create'), {
            'issue_type': 'garbage',
            'description': 'test',
            'latitude': 18.5204,
            'longitude': 73.8567,
        })
        # should redirect to login
        self.assertNotEqual(response.status_code, 200)


class ComplaintAPITest(TestCase):
    """Tests for the REST API endpoints"""

    def setUp(self):
        self.client = Client()
        self.citizen = CustomUser.objects.create_user(
            username='apicitzen',
            password='test1234',
            role='citizen'
        )
        self.complaint = Complaint.objects.create(
            user=self.citizen,
            issue_type='water',
            description='No water supply',
            latitude=18.5204,
            longitude=73.8567,
        )

    def test_api_requires_authentication(self):
        """API should return 403 for unauthenticated requests"""
        response = self.client.get('/api/complaints/')
        self.assertEqual(response.status_code, 403)

    def test_api_returns_json(self):
        """API should return JSON content type"""
        self.client.login(username='apicitzen', password='test1234')
        response = self.client.get('/api/complaints/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')

    def test_api_returns_correct_complaint(self):
        """API should return the citizen's own complaints"""
        self.client.login(username='apicitzen', password='test1234')
        response = self.client.get('/api/complaints/')
        data = response.json()
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]['description'], 'No water supply')