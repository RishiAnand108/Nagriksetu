# users/tests.py
from django.test import Client, TestCase
from django.urls import reverse

from complaints.models import Ward

from .models import CustomUser


class CustomUserModelTest(TestCase):
    def test_default_role_is_citizen(self):
        user = CustomUser.objects.create_user(username='u1', password='test1234')
        self.assertEqual(user.role, 'citizen')
        self.assertTrue(user.is_citizen)
        self.assertFalse(user.is_corporator)

    def test_corporator_flag(self):
        user = CustomUser.objects.create_user(username='u2', password='test1234', role='corporator')
        self.assertTrue(user.is_corporator)

    def test_str_shows_role_label(self):
        user = CustomUser.objects.create_user(username='u3', password='test1234', role='corporator')
        self.assertEqual(str(user), 'u3 (Corporator)')

    def test_display_name_prefers_full_name(self):
        user = CustomUser.objects.create_user(
            username='u4', password='test1234', first_name='Asha', last_name='Patil'
        )
        self.assertEqual(user.display_name, 'Asha Patil')

        bare = CustomUser.objects.create_user(username='u5', password='test1234')
        self.assertEqual(bare.display_name, 'u5')


class SignupViewTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.url = reverse('signup')

    def _payload(self, **overrides):
        data = {
            'username': 'newcitizen',
            'email': 'new@example.com',
            'phone': '9876543210',
            'password1': 'Str0ng!Passphrase',
            'password2': 'Str0ng!Passphrase',
        }
        data.update(overrides)
        return data

    def test_page_renders(self):
        self.assertEqual(self.client.get(self.url).status_code, 200)

    def test_signup_creates_and_logs_in(self):
        response = self.client.post(self.url, self._payload())
        self.assertEqual(response.status_code, 302)
        user = CustomUser.objects.get(username='newcitizen')
        self.assertEqual(self.client.session['_auth_user_id'], str(user.pk))

    def test_role_cannot_be_escalated_through_the_form(self):
        """A posted role must never turn a citizen into a corporator."""
        self.client.post(self.url, self._payload(role='corporator'))
        self.assertEqual(CustomUser.objects.get(username='newcitizen').role, 'citizen')

    def test_duplicate_email_is_rejected(self):
        CustomUser.objects.create_user(username='existing', password='test1234', email='new@example.com')
        response = self.client.post(self.url, self._payload())
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'already exists')

    def test_invalid_phone_is_rejected(self):
        response = self.client.post(self.url, self._payload(phone='12345'))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(CustomUser.objects.filter(username='newcitizen').exists())

    def test_ward_can_be_chosen(self):
        ward = Ward.objects.create(number=3, name='Aundh')
        self.client.post(self.url, self._payload(ward=ward.pk))
        self.assertEqual(CustomUser.objects.get(username='newcitizen').ward, ward)

    def test_signed_in_user_is_redirected_away(self):
        CustomUser.objects.create_user(username='already', password='test1234')
        self.client.login(username='already', password='test1234')
        self.assertEqual(self.client.get(self.url).status_code, 302)


class LoginLogoutTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = CustomUser.objects.create_user(username='loginuser', password='test1234')

    def test_login_succeeds(self):
        response = self.client.post(reverse('login'), {'username': 'loginuser', 'password': 'test1234'})
        self.assertEqual(response.status_code, 302)
        self.assertIn('_auth_user_id', self.client.session)

    def test_login_failure_re_renders(self):
        response = self.client.post(reverse('login'), {'username': 'loginuser', 'password': 'wrong'})
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('_auth_user_id', self.client.session)

    def test_logout_rejects_get(self):
        """Regression: logout used to happen on GET, which any prefetch could fire."""
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(reverse('logout')).status_code, 405)
        self.assertIn('_auth_user_id', self.client.session)

    def test_logout_works_on_post(self):
        self.client.force_login(self.user)
        response = self.client.post(reverse('logout'))
        self.assertEqual(response.status_code, 302)
        self.assertNotIn('_auth_user_id', self.client.session)

    def test_next_must_stay_on_this_site(self):
        response = self.client.post(
            reverse('login') + '?next=https://evil.example.com/',
            {'username': 'loginuser', 'password': 'test1234'},
        )
        self.assertNotIn('evil.example.com', response['Location'])


class ProfileViewTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = CustomUser.objects.create_user(username='profileuser', password='test1234')

    def test_requires_login(self):
        self.assertEqual(self.client.get(reverse('profile')).status_code, 302)

    def test_renders_for_signed_in_user(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse('profile'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'profileuser')

    def test_update_saves_changes(self):
        self.client.force_login(self.user)
        self.client.post(reverse('profile'), {
            'first_name': 'Asha', 'last_name': 'Patil',
            'email': 'asha@example.com', 'phone': '9876543210',
            'notify_by_email': 'on',
        })
        self.user.refresh_from_db()
        self.assertEqual(self.user.first_name, 'Asha')
        self.assertEqual(self.user.email, 'asha@example.com')


class AccountAPITest(TestCase):
    def setUp(self):
        self.client = Client()

    def _payload(self, **overrides):
        data = {
            'username': 'apiuser',
            'email': 'apiuser@example.com',
            'phone': '9876543210',
            'password': 'Str0ng!Passphrase',
            'password_confirm': 'Str0ng!Passphrase',
        }
        data.update(overrides)
        return data

    def test_register_returns_tokens(self):
        response = self.client.post(
            '/api/auth/register/', self._payload(),
            content_type='application/json', headers={'accept': 'application/json'},
        )
        self.assertEqual(response.status_code, 201)
        body = response.json()
        self.assertIn('access', body)
        self.assertIn('refresh', body)
        self.assertEqual(body['user']['role'], 'citizen')

    def test_register_rejects_mismatched_passwords(self):
        response = self.client.post(
            '/api/auth/register/', self._payload(password_confirm='different'),
            content_type='application/json', headers={'accept': 'application/json'},
        )
        self.assertEqual(response.status_code, 400)

    def test_register_rejects_weak_password(self):
        response = self.client.post(
            '/api/auth/register/', self._payload(password='123', password_confirm='123'),
            content_type='application/json', headers={'accept': 'application/json'},
        )
        self.assertEqual(response.status_code, 400)

    def test_me_requires_authentication(self):
        response = self.client.get('/api/auth/me/', headers={'accept': 'application/json'})
        self.assertIn(response.status_code, (401, 403))

    def test_me_returns_own_profile(self):
        user = CustomUser.objects.create_user(username='meuser', password='test1234')
        self.client.force_login(user)
        data = self.client.get('/api/auth/me/', headers={'accept': 'application/json'}).json()
        self.assertEqual(data['username'], 'meuser')

    def test_role_is_read_only_over_the_api(self):
        user = CustomUser.objects.create_user(username='meuser2', password='test1234')
        self.client.force_login(user)
        self.client.patch(
            '/api/auth/me/', {'role': 'corporator'},
            content_type='application/json', headers={'accept': 'application/json'},
        )
        user.refresh_from_db()
        self.assertEqual(user.role, 'citizen')

    def test_jwt_token_endpoint(self):
        CustomUser.objects.create_user(username='jwtuser', password='Str0ng!Passphrase')
        response = self.client.post(
            '/api/auth/token/', {'username': 'jwtuser', 'password': 'Str0ng!Passphrase'},
            content_type='application/json', headers={'accept': 'application/json'},
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn('access', response.json())
