from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.db.models.signals import post_migrate, post_save
from django.dispatch import receiver
from .models import Profile


ADMIN_PERMISSION_APPS = ("auth", "authtoken", "tickets")


def sync_admin_permissions(profile):
    permissions = Permission.objects.filter(content_type__app_label__in=ADMIN_PERMISSION_APPS)
    if profile.role == Profile.Role.ADMIN:
        profile.user.user_permissions.add(*permissions)
    else:
        profile.user.user_permissions.remove(*permissions)


@receiver(post_save, sender=get_user_model())
def create_profile(sender, instance, created, **kwargs):
    if created:
        Profile.objects.create(user=instance, role=Profile.Role.ADMIN if instance.is_superuser else Profile.Role.REQUESTER)


@receiver(post_save, sender=Profile)
def update_admin_permissions(sender, instance, **kwargs):
    sync_admin_permissions(instance)


@receiver(post_migrate)
def update_existing_admin_permissions(sender, **kwargs):
    if sender.name != "tickets":
        return
    for profile in Profile.objects.select_related("user"):
        sync_admin_permissions(profile)
