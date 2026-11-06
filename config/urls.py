from django.conf import settings
from django.contrib import admin
from django.contrib.staticfiles.urls import staticfiles_urlpatterns
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView
from rest_framework.permissions import IsAdminUser
from tickets.api_tokens import ObtainExpiringAuthToken
from django.http import JsonResponse
from django.views.decorators.http import require_GET


@require_GET
def health(request):
    from django.db import connection
    connection.ensure_connection()
    return JsonResponse({"status": "ok", "database": "ok"})

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("tickets.urls")),
    path("api/v1/", include("tickets.api_urls")),
    path("api/token/", ObtainExpiringAuthToken.as_view(), name="api-token"),
    path("health/", health, name="health"),
    path("api/schema/", SpectacularAPIView.as_view(permission_classes=[IsAdminUser]), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema", permission_classes=[IsAdminUser]), name="api-docs"),
]
if settings.DEBUG:
    urlpatterns += staticfiles_urlpatterns()
