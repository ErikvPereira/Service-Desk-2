from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone
from .models import AuditLog, Profile, Ticket

TRANSITIONS = {
    Ticket.Status.OPEN: {Ticket.Status.IN_PROGRESS, Ticket.Status.CLOSED},
    Ticket.Status.IN_PROGRESS: {Ticket.Status.WAITING, Ticket.Status.RESOLVED, Ticket.Status.CLOSED},
    Ticket.Status.WAITING: {Ticket.Status.IN_PROGRESS, Ticket.Status.RESOLVED, Ticket.Status.CLOSED},
    Ticket.Status.RESOLVED: {Ticket.Status.CLOSED, Ticket.Status.IN_PROGRESS},
    Ticket.Status.CLOSED: {Ticket.Status.IN_PROGRESS},
}


def is_staff_member(user):
    return user.is_superuser or (hasattr(user, "profile") and user.profile.can_manage_tickets)


def visible_tickets(user):
    queryset = Ticket.objects.select_related("requester", "assignee", "category")
    return queryset if is_staff_member(user) else queryset.filter(requester=user)


def audit(ticket, actor, action, field="", previous="", new=""):
    AuditLog.objects.create(ticket=ticket, actor=actor, action=action, field=field, previous_value=str(previous or ""), new_value=str(new or ""))


@transaction.atomic
def update_ticket(ticket, actor, **changes):
    if not is_staff_member(actor):
        raise PermissionDenied("Somente agentes e administradores podem atualizar chamados.")
    status = changes.pop("status", None)
    for field, value in changes.items():
        old = getattr(ticket, field)
        if old != value:
            setattr(ticket, field, value)
            if field == "assignee" and value:
                ticket.assigned_at = timezone.now()
            audit(ticket, actor, "Campo atualizado", field, old, value)
    if status and status != ticket.status:
        if status not in TRANSITIONS[ticket.status]:
            raise ValidationError({"status": f"Transição de {ticket.get_status_display()} não permitida."})
        previous = ticket.status
        ticket.status = status
        if status == Ticket.Status.RESOLVED:
            ticket.resolved_at = timezone.now()
        if status == Ticket.Status.CLOSED:
            ticket.closed_at = timezone.now()
        if status == Ticket.Status.IN_PROGRESS and previous == Ticket.Status.CLOSED:
            ticket.closed_at = None
            audit(ticket, actor, "Chamado reaberto", "status", previous, status)
        else:
            audit(ticket, actor, "Status alterado", "status", previous, status)
    ticket.full_clean()
    ticket.save()
    return ticket
