# users/api.py
"""Account endpoints: register, JWT sign-in/refresh/sign-out, and your own profile."""
from django.contrib.auth.password_validation import validate_password
from drf_spectacular.utils import extend_schema
from rest_framework import serializers, status
from rest_framework.generics import RetrieveUpdateAPIView
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenBlacklistView, TokenObtainPairView, TokenRefreshView

from . import services
from .models import CustomUser, Role


class MeSerializer(serializers.ModelSerializer):
    ward_label = serializers.SerializerMethodField()
    complaint_count = serializers.IntegerField(source='complaints.count', read_only=True)

    class Meta:
        model = CustomUser
        fields = [
            'id', 'username', 'first_name', 'last_name', 'email', 'email_verified', 'phone',
            'role', 'ward', 'ward_label', 'notify_by_email', 'complaint_count',
            'date_joined',
        ]
        # Role and verification are server-controlled: nobody promotes or verifies themselves.
        read_only_fields = ['id', 'username', 'role', 'email_verified', 'date_joined']

    def get_ward_label(self, obj) -> str:
        return str(obj.ward) if obj.ward_id else ''

    def validate_email(self, value):
        value = (value or '').strip()
        if services.email_in_use(value, exclude_pk=getattr(self.instance, 'pk', None)):
            raise serializers.ValidationError('Another account already uses this email.')
        return value

    def validate_ward(self, value):
        # A corporator's ward is their jurisdiction; only staff may change it.
        if self.instance and self.instance.role == Role.CORPORATOR and value != self.instance.ward:
            raise serializers.ValidationError('Your jurisdiction is assigned by the municipal administrator.')
        return value

    def update(self, instance, validated_data):
        email_changed = False
        if 'email' in validated_data:
            email_changed = services.apply_email_change(instance, validated_data.pop('email'))
        instance = super().update(instance, validated_data)
        if email_changed and instance.email:
            services.send_verification_email(self.context['request'], instance)
        return instance


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, style={'input_type': 'password'})
    password_confirm = serializers.CharField(write_only=True, style={'input_type': 'password'})

    class Meta:
        model = CustomUser
        fields = ['username', 'email', 'phone', 'ward', 'password', 'password_confirm']

    def validate_email(self, value):
        value = (value or '').strip()
        if services.email_in_use(value):
            raise serializers.ValidationError('An account with this email already exists.')
        return value

    def validate(self, attrs):
        if attrs['password'] != attrs.pop('password_confirm'):
            raise serializers.ValidationError({'password_confirm': 'Passwords do not match.'})
        validate_password(attrs['password'])
        return attrs

    def create(self, validated_data):
        password = validated_data.pop('password')
        user = CustomUser(**validated_data, role=Role.CITIZEN)
        user.set_password(password)
        user.save()
        return user


@extend_schema(
    summary='Register a citizen account',
    description='Returns the new profile and a JWT pair. If an email is given, a confirmation link is sent; '
                'notifications are only delivered to confirmed addresses.',
    request=RegisterSerializer,
    responses={201: MeSerializer},
    auth=[],
)
class RegisterAPIView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'register'

    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        services.send_verification_email(request, user)
        refresh = RefreshToken.for_user(user)
        return Response(
            {
                'user': MeSerializer(user, context={'request': request}).data,
                'refresh': str(refresh),
                'access': str(refresh.access_token),
            },
            status=status.HTTP_201_CREATED,
        )


@extend_schema(summary='Read or update your own profile')
class MeAPIView(RetrieveUpdateAPIView):
    serializer_class = MeSerializer
    permission_classes = [IsAuthenticated]

    def get_object(self):
        return self.request.user


@extend_schema(
    summary='Obtain a JWT pair',
    description='Send `{"username", "password"}`. Use the access token as `Authorization: Bearer <token>`. '
                'Rate-limited per client.',
)
class LoginAPIView(TokenObtainPairView):
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'login'


@extend_schema(
    summary='Rotate a refresh token',
    description='Returns a new access token and a new refresh token; the old refresh token is blacklisted.',
)
class RefreshAPIView(TokenRefreshView):
    pass


@extend_schema(
    summary='Sign out (revoke a refresh token)',
    description='Blacklists the given refresh token so it can no longer mint access tokens. '
                'Access tokens expire on their own shortly after.',
)
class LogoutAPIView(TokenBlacklistView):
    pass


@extend_schema(deprecated=True, summary='Deprecated alias of /api/auth/token/')
class LegacyLoginAPIView(LoginAPIView):
    pass


@extend_schema(deprecated=True, summary='Deprecated alias of /api/auth/token/refresh/')
class LegacyRefreshAPIView(RefreshAPIView):
    pass
