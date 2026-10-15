from django.contrib import admin
from .models import AuditLog, Category, Comment, Profile, Ticket


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "role")
    list_filter = ("role",)


@admin.register(Ticket)
class TicketAdmin(admin.ModelAdmin):
    list_display = ("number", "title", "status", "priority", "requester", "assignee", "created_at")
    list_filter = ("status", "priority", "category")
    search_fields = ("number", "title", "requester__username")
    readonly_fields = ("number", "created_at", "updated_at", "assigned_at", "resolved_at", "closed_at")


admin.site.register(Category)
admin.site.register(Comment)
@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ("ticket", "action", "field", "actor", "created_at")
    readonly_fields = ("ticket", "action", "field", "previous_value", "new_value", "actor", "created_at")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
