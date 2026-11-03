from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from django.contrib.auth import get_user_model
from rest_framework.authtoken.models import Token
from .models import AuditLog, Category, Comment, Profile, Ticket

admin.site.site_header = "ServiceDesk · Administração"
admin.site.site_title = "ServiceDesk Admin"
admin.site.index_title = "Gerenciar ServiceDesk"
admin.site.unregister(get_user_model())


def is_service_admin(request):
    user = request.user
    return user.is_active and (
        user.is_superuser
        or (hasattr(user, "profile") and user.profile.role == Profile.Role.ADMIN)
    )


class ServiceAdminPermissionsMixin:
    def has_module_permission(self, request):
        return is_service_admin(request)

    def has_view_permission(self, request, obj=None):
        return is_service_admin(request)

    def has_add_permission(self, request):
        return is_service_admin(request)

    def has_change_permission(self, request, obj=None):
        return is_service_admin(request)

    def has_delete_permission(self, request, obj=None):
        return is_service_admin(request)


@admin.register(Token)
class APITokenAdmin(admin.ModelAdmin):
    list_display = ("user", "created")
    search_fields = ("user__username", "user__email")
    readonly_fields = ("key", "created", "user")
    fields = ("key", "created", "user")

    def has_add_permission(self, request):
        return False


@admin.register(get_user_model())
class UserAdmin(DjangoUserAdmin):
    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        if not request.user.is_superuser:
            for restricted in ("is_staff", "is_superuser", "user_permissions", "groups"):
                form.base_fields.pop(restricted, None)
        return form

    def has_module_permission(self, request):
        return request.user.is_superuser or (hasattr(request.user, "profile") and request.user.profile.role == Profile.Role.ADMIN)

    def has_view_permission(self, request, obj=None):
        return self.has_module_permission(request)

    def has_add_permission(self, request):
        return self.has_module_permission(request)

    def has_change_permission(self, request, obj=None):
        if not self.has_module_permission(request):
            return False
        if obj and obj.is_superuser and not request.user.is_superuser:
            return False
        return True

    def has_delete_permission(self, request, obj=None):
        if not is_service_admin(request):
            return False
        return not obj or not obj.is_superuser or request.user.is_superuser


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "role")
    list_filter = ("role",)

    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        if not request.user.is_superuser and "role" in form.base_fields:
            form.base_fields["role"].choices = [choice for choice in form.base_fields["role"].choices if choice[0] != Profile.Role.ADMIN]
        return form

    def has_module_permission(self, request):
        return request.user.is_superuser or (hasattr(request.user, "profile") and request.user.profile.role == Profile.Role.ADMIN)

    def has_add_permission(self, request):
        return self.has_module_permission(request)

    def has_change_permission(self, request, obj=None):
        if not self.has_module_permission(request):
            return False
        if obj and obj.role == Profile.Role.ADMIN and not request.user.is_superuser:
            return False
        return True

    def has_delete_permission(self, request, obj=None):
        if not is_service_admin(request):
            return False
        return not obj or obj.role != Profile.Role.ADMIN or request.user.is_superuser


@admin.register(Ticket)
class TicketAdmin(ServiceAdminPermissionsMixin, admin.ModelAdmin):
    list_display = ("number", "title", "status", "priority", "requester", "assignee", "created_at")
    list_filter = ("status", "priority", "category")
    search_fields = ("number", "title", "requester__username")
    readonly_fields = ("number", "created_at", "updated_at", "assigned_at", "first_response_at", "resolved_at", "closed_at")

    def has_delete_permission(self, request, obj=None):
        return is_service_admin(request)


@admin.register(Category)
class CategoryAdmin(ServiceAdminPermissionsMixin, admin.ModelAdmin):
    list_display = ("name", "active")
    list_filter = ("active",)
    search_fields = ("name",)


@admin.register(Comment)
class CommentAdmin(ServiceAdminPermissionsMixin, admin.ModelAdmin):
    list_display = ("ticket", "author", "internal", "created_at", "updated_at")
    readonly_fields = ("created_at", "updated_at")

    def save_model(self, request, obj, form, change):
        if change:
            old = Comment.objects.get(pk=obj.pk)
            if old.body != obj.body:
                AuditLog.objects.create(ticket=obj.ticket, actor=request.user, action="Comentário editado", field="comment", previous_value=old.body, new_value=obj.body)
        super().save_model(request, obj, form, change)

    def delete_model(self, request, obj):
        AuditLog.objects.create(ticket=obj.ticket, actor=request.user, action="Comentário excluído", field="comment", previous_value=obj.body)
        super().delete_model(request, obj)

    def delete_queryset(self, request, queryset):
        for obj in queryset.select_related("ticket"):
            AuditLog.objects.create(ticket=obj.ticket, actor=request.user, action="Comentário excluído", field="comment", previous_value=obj.body)
        queryset.delete()
@admin.register(AuditLog)
class AuditLogAdmin(ServiceAdminPermissionsMixin, admin.ModelAdmin):
    list_display = ("ticket", "action", "field", "actor", "created_at")
    readonly_fields = ("ticket", "action", "field", "previous_value", "new_value", "actor", "created_at")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return is_service_admin(request)
