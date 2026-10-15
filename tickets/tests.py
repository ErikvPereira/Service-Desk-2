import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.urls import reverse
from rest_framework.test import APIClient
from .models import AuditLog, Category, Profile, Ticket
from .services import update_ticket

User = get_user_model()


@pytest.fixture
def category(db):
    return Category.objects.create(name="Infraestrutura")


@pytest.fixture
def requester(db):
    return User.objects.create_user("solicitante", password="safe-password-123")


@pytest.fixture
def agent(db):
    user = User.objects.create_user("agente", password="safe-password-123")
    user.profile.role = Profile.Role.AGENT
    user.profile.save()
    return user


@pytest.fixture
def ticket(category, requester):
    return Ticket.objects.create(title="Sem conexão de rede", description="A rede caiu no segundo andar.", category=category, requester=requester)


@pytest.mark.django_db
def test_ticket_gets_unique_service_number(ticket):
    assert ticket.number == "SD-000001"


@pytest.mark.django_db
def test_agent_can_follow_valid_lifecycle(ticket, agent):
    update_ticket(ticket, agent, status=Ticket.Status.IN_PROGRESS, assignee=agent)
    ticket.refresh_from_db()
    assert ticket.status == Ticket.Status.IN_PROGRESS
    assert ticket.assignee == agent
    assert ticket.assigned_at is not None
    assert ticket.audit_logs.count() == 2


@pytest.mark.django_db
def test_invalid_status_transition_is_rejected(ticket, agent):
    with pytest.raises(ValidationError):
        update_ticket(ticket, agent, status=Ticket.Status.RESOLVED)


@pytest.mark.django_db
def test_requester_cannot_change_ticket(ticket, requester):
    with pytest.raises(Exception):
        update_ticket(ticket, requester, status=Ticket.Status.IN_PROGRESS)


@pytest.mark.django_db
def test_requester_only_sees_own_tickets(client, requester, category):
    other = User.objects.create_user("other", password="safe-password-123")
    own = Ticket.objects.create(title="Meu chamado", description="x", category=category, requester=requester)
    hidden = Ticket.objects.create(title="Chamado alheio", description="x", category=category, requester=other)
    client.force_login(requester)
    response = client.get(reverse("ticket-list"))
    assert response.status_code == 200
    assert own.number in response.content.decode()
    assert hidden.number not in response.content.decode()


@pytest.mark.django_db
def test_api_enforces_visibility(ticket, requester, category):
    other = User.objects.create_user("other-api", password="safe-password-123")
    hidden = Ticket.objects.create(title="Privado", description="x", category=category, requester=other)
    client = APIClient()
    client.force_authenticate(requester)
    response = client.get("/api/v1/tickets/")
    assert response.status_code == 200
    assert [item["id"] for item in response.data["results"]] == [ticket.id]
    assert client.get(f"/api/v1/tickets/{hidden.pk}/").status_code == 404


@pytest.mark.django_db
def test_audit_record_is_immutable(ticket, requester):
    audit = AuditLog.objects.create(ticket=ticket, actor=requester, action="Chamado criado")
    audit.action = "Alterado"
    with pytest.raises(ValidationError):
        audit.save()
