from django.urls import include, path
from rest_framework.routers import DefaultRouter
from .api_views import AuditViewSet, CategoryViewSet, CommentViewSet, TicketViewSet

router = DefaultRouter()
router.register("tickets", TicketViewSet, basename="api-ticket")
router.register("comments", CommentViewSet, basename="api-comment")
router.register("categories", CategoryViewSet, basename="api-category")
router.register("audits", AuditViewSet, basename="api-audit")
urlpatterns = [path("", include(router.urls))]
