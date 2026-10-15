from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


class Profile(models.Model):
    class Role(models.TextChoices):
        ADMIN = "admin", "Administrador"
        AGENT = "agent", "Agente de suporte"
        REQUESTER = "requester", "Solicitante"

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="profile")
    role = models.CharField(max_length=16, choices=Role.choices, default=Role.REQUESTER)

    @property
    def can_manage_tickets(self):
        return self.role in {self.Role.ADMIN, self.Role.AGENT}

    def __str__(self):
        return f"{self.user.get_full_name() or self.user.username} ({self.get_role_display()})"


class Category(models.Model):
    name = models.CharField(max_length=80, unique=True)
    active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class Ticket(models.Model):
    class Priority(models.TextChoices):
        LOW = "low", "Baixa"
        MEDIUM = "medium", "Média"
        HIGH = "high", "Alta"
        CRITICAL = "critical", "Crítica"

    class Status(models.TextChoices):
        OPEN = "open", "Aberto"
        IN_PROGRESS = "in_progress", "Em andamento"
        WAITING = "waiting", "Aguardando solicitante"
        RESOLVED = "resolved", "Resolvido"
        CLOSED = "closed", "Encerrado"

    number = models.CharField(max_length=16, unique=True, editable=False)
    title = models.CharField(max_length=180)
    description = models.TextField()
    category = models.ForeignKey(Category, on_delete=models.PROTECT, related_name="tickets")
    requester = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="requested_tickets")
    assignee = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, related_name="assigned_tickets", null=True, blank=True)
    priority = models.CharField(max_length=12, choices=Priority.choices, default=Priority.MEDIUM)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.OPEN)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    assigned_at = models.DateTimeField(null=True, blank=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    closed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status", "priority"], name="tickets_tic_status_54e5a0_idx"),
            models.Index(fields=["requester", "created_at"], name="tickets_tic_request_4f7fd0_idx"),
        ]

    def save(self, *args, **kwargs):
        if not self.number:
            last = Ticket.objects.order_by("-id").values_list("id", flat=True).first() or 0
            self.number = f"SD-{last + 1:06d}"
        super().save(*args, **kwargs)

    def clean(self):
        if self.assignee and (not self.assignee.is_active or not hasattr(self.assignee, "profile") or self.assignee.profile.role not in {Profile.Role.AGENT, Profile.Role.ADMIN}):
            raise ValidationError({"assignee": "O responsável deve ser um agente ativo ou administrador."})

    @property
    def elapsed(self):
        end = self.closed_at or self.resolved_at or timezone.now()
        return end - self.created_at

    def __str__(self):
        return f"{self.number} — {self.title}"


class Comment(models.Model):
    ticket = models.ForeignKey(Ticket, on_delete=models.CASCADE, related_name="comments")
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="ticket_comments")
    body = models.TextField(max_length=4000)
    internal = models.BooleanField(default=False, help_text="Visível somente a agentes e administradores.")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]


class AuditLog(models.Model):
    ticket = models.ForeignKey(Ticket, on_delete=models.CASCADE, related_name="audit_logs")
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="ticket_audits")
    action = models.CharField(max_length=80)
    field = models.CharField(max_length=80, blank=True)
    previous_value = models.TextField(blank=True)
    new_value = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]
        verbose_name = "Registro de auditoria"
        verbose_name_plural = "Registros de auditoria"

    def save(self, *args, **kwargs):
        if self.pk:
            raise ValidationError("Registros de auditoria são imutáveis.")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Registros de auditoria não podem ser excluídos.")
