from django.conf import settings
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache
from rest_framework import serializers
from rest_framework.authentication import TokenAuthentication
from rest_framework.authtoken.models import Token
from rest_framework.authtoken.serializers import AuthTokenSerializer
from rest_framework.authtoken.views import ObtainAuthToken
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle


class ExpiringTokenAuthentication(TokenAuthentication):
    def authenticate_credentials(self, key):
        user, token = super().authenticate_credentials(key)
        if token.created + settings.API_TOKEN_LIFETIME <= timezone.now():
            token.delete()
            raise AuthenticationFailed("O token expirou. Gere um novo token para esta integração.")
        return user, token


@method_decorator(never_cache, name="dispatch")
class ObtainExpiringAuthToken(ObtainAuthToken):
    serializer_class = AuthTokenSerializer
    permission_classes = [AllowAny]
    throttle_classes = [AnonRateThrottle]

    def post(self, request, *args, **kwargs):
        serializer = self.serializer_class(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data["user"]
        token = Token.objects.filter(user=user).first()
        if token and token.created + settings.API_TOKEN_LIFETIME <= timezone.now():
            token.delete()
            token = None
        if token is None:
            token = Token.objects.create(user=user)
        expires_at = token.created + settings.API_TOKEN_LIFETIME
        return Response({"token": token.key, "expires_at": serializers.DateTimeField().to_representation(expires_at)})
