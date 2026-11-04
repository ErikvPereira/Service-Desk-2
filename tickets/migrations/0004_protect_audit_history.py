from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def remove_role_granted_permissions(apps, schema_editor):
    User = apps.get_model(*settings.AUTH_USER_MODEL.split("."))
    Permission = apps.get_model("auth", "Permission")
    app_permissions = Permission.objects.filter(content_type__app_label__in=("auth", "authtoken", "tickets"))
    User.user_permissions.through.objects.filter(permission__in=app_permissions).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("tickets", "0003_default_categories"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AlterField(
            model_name="auditlog",
            name="ticket",
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="audit_logs", to="tickets.ticket"),
        ),
        migrations.RunPython(remove_role_granted_permissions, migrations.RunPython.noop),
    ]
