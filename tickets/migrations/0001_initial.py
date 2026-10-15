# Generated manually for the Service Desk initial schema.
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True
    dependencies = [migrations.swappable_dependency(settings.AUTH_USER_MODEL)]
    operations = [
        migrations.CreateModel(name="Category", fields=[
            ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
            ("name", models.CharField(max_length=80, unique=True)), ("active", models.BooleanField(default=True)),
        ], options={"ordering": ["name"]}),
        migrations.CreateModel(name="Profile", fields=[
            ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
            ("role", models.CharField(choices=[("admin", "Administrador"), ("agent", "Agente de suporte"), ("requester", "Solicitante")], default="requester", max_length=16)),
            ("user", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="profile", to=settings.AUTH_USER_MODEL)),
        ]),
        migrations.CreateModel(name="Ticket", fields=[
            ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
            ("number", models.CharField(editable=False, max_length=16, unique=True)), ("title", models.CharField(max_length=180)),
            ("description", models.TextField()), ("priority", models.CharField(choices=[("low", "Baixa"), ("medium", "Média"), ("high", "Alta"), ("critical", "Crítica")], default="medium", max_length=12)),
            ("status", models.CharField(choices=[("open", "Aberto"), ("in_progress", "Em andamento"), ("waiting", "Aguardando solicitante"), ("resolved", "Resolvido"), ("closed", "Encerrado")], default="open", max_length=16)),
            ("created_at", models.DateTimeField(auto_now_add=True)), ("updated_at", models.DateTimeField(auto_now=True)), ("assigned_at", models.DateTimeField(blank=True, null=True)), ("resolved_at", models.DateTimeField(blank=True, null=True)), ("closed_at", models.DateTimeField(blank=True, null=True)),
            ("assignee", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="assigned_tickets", to=settings.AUTH_USER_MODEL)),
            ("category", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="tickets", to="tickets.category")),
            ("requester", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="requested_tickets", to=settings.AUTH_USER_MODEL)),
        ], options={"ordering": ["-created_at"]}),
        migrations.AddIndex(model_name="ticket", index=models.Index(fields=["status", "priority"], name="tickets_tic_status_54e5a0_idx")),
        migrations.AddIndex(model_name="ticket", index=models.Index(fields=["requester", "created_at"], name="tickets_tic_request_4f7fd0_idx")),
        migrations.CreateModel(name="Comment", fields=[
            ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")), ("body", models.TextField(max_length=4000)), ("internal", models.BooleanField(default=False, help_text="Visível somente a agentes e administradores.")), ("created_at", models.DateTimeField(auto_now_add=True)),
            ("author", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="ticket_comments", to=settings.AUTH_USER_MODEL)), ("ticket", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="comments", to="tickets.ticket")),
        ], options={"ordering": ["created_at"]}),
        migrations.CreateModel(name="AuditLog", fields=[
            ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")), ("action", models.CharField(max_length=80)), ("field", models.CharField(blank=True, max_length=80)), ("previous_value", models.TextField(blank=True)), ("new_value", models.TextField(blank=True)), ("created_at", models.DateTimeField(auto_now_add=True)),
            ("actor", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="ticket_audits", to=settings.AUTH_USER_MODEL)), ("ticket", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="audit_logs", to="tickets.ticket")),
        ], options={"ordering": ["created_at"], "verbose_name": "Registro de auditoria", "verbose_name_plural": "Registros de auditoria"}),
    ]
