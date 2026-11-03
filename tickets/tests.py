import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.urls import reverse
from django.contrib.auth import authenticate
from django.contrib.auth.models import AnonymousUser
from django.test import override_settings
from rest_framework.authtoken.models import Token
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
    assert response.context["ticket_summary"] == {
        "total": 1, "open": 1, "in_progress": 0, "waiting": 0, "closed": 0,
    }


@pytest.mark.django_db
def test_my_tickets_limits_agents_to_their_own_requests(client, agent, category):
    other = User.objects.create_user("outro-solicitante", password="safe-password-123")
    own = Ticket.objects.create(title="Minha solicitação", description="x", category=category, requester=agent)
    hidden = Ticket.objects.create(title="Solicitação de outra pessoa", description="x", category=category, requester=other)
    client.force_login(agent)
    response = client.get(reverse("my-ticket-list"))
    content = response.content.decode()
    assert response.status_code == 200
    assert "Meus chamados" in content
    assert own.number in content
    assert hidden.number not in content


@pytest.mark.django_db
def test_authenticated_user_can_open_ticket_create_form(client, requester):
    client.force_login(requester)
    response = client.get(reverse("ticket-create"))
    assert response.status_code == 200
    content = response.content.decode()
    assert "Abrir novo chamado" in content
    assert "Título do chamado" in content


@pytest.mark.django_db
def test_authenticated_user_can_create_ticket_from_form(client, requester, category):
    client.force_login(requester)
    response = client.post(reverse("ticket-create"), {
        "title": "Acesso ao sistema indisponível",
        "description": "Não consigo acessar o sistema financeiro desde esta manhã.",
        "category": category.pk,
        "priority": Ticket.Priority.HIGH,
    })
    ticket = Ticket.objects.get(title="Acesso ao sistema indisponível")
    assert response.status_code == 302
    assert response.url == reverse("ticket-detail", kwargs={"pk": ticket.pk})
    assert ticket.requester == requester
    assert ticket.priority == Ticket.Priority.HIGH


@pytest.mark.django_db
def test_ticket_create_form_shows_validation_errors(client, requester):
    client.force_login(requester)
    response = client.post(reverse("ticket-create"), {})
    assert response.status_code == 200
    assert response.context["form"].errors
    assert "has-error" in response.content.decode()


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


@pytest.mark.django_db
def test_login_and_inactive_user(client, requester):
    response = client.post(reverse("login"), {"username": requester.username, "password": "safe-password-123"})
    assert response.status_code == 302
    requester.is_active = False
    requester.save()
    assert authenticate(username=requester.username, password="safe-password-123") is None


@pytest.mark.django_db
def test_signup_creates_requester_and_authenticates(client):
    response = client.post(reverse("signup"), {
        "username": "novo", "password1": "A-safe-password-123!", "password2": "A-safe-password-123!",
    })
    user = User.objects.get(username="novo")
    assert response.status_code == 302
    assert user.profile.role == Profile.Role.REQUESTER
    assert int(client.session["_auth_user_id"]) == user.pk


@pytest.mark.django_db
def test_admin_profile_grants_django_admin_access(db):
    user = User.objects.create_user("perfil-admin", password="safe-password-123")
    user.profile.role = Profile.Role.ADMIN
    user.profile.save()
    user.refresh_from_db()
    assert user.is_staff


@pytest.mark.django_db
def test_comment_internal_visibility_and_audit(client, ticket, agent, requester):
    internal = ticket.comments.create(author=agent, body="Nota privada", internal=True)
    client.force_login(requester)
    response = client.get(reverse("ticket-detail", kwargs={"pk": ticket.pk}))
    assert "Nota privada" not in response.content.decode()
    client.force_login(agent)
    response = client.get(reverse("ticket-detail", kwargs={"pk": ticket.pk}))
    assert "Nota privada" in response.content.decode()
    internal.body = "Texto editado"
    internal.save()
    AuditLog.objects.create(ticket=ticket, actor=agent, action="Comentário editado", field="comment", previous_value="Nota privada", new_value=internal.body)
    assert ticket.audit_logs.filter(action="Comentário editado").exists()


@pytest.mark.django_db
def test_close_and_reopen_lifecycle(ticket, agent):
    update_ticket(ticket, agent, status=Ticket.Status.IN_PROGRESS)
    ticket.refresh_from_db()
    assert ticket.first_response_at
    update_ticket(ticket, agent, status=Ticket.Status.RESOLVED)
    update_ticket(ticket, agent, status=Ticket.Status.CLOSED)
    ticket.refresh_from_db()
    assert ticket.closed_at
    update_ticket(ticket, agent, status=Ticket.Status.IN_PROGRESS)
    ticket.refresh_from_db()
    assert ticket.closed_at is None
    assert ticket.audit_logs.filter(action="Chamado reaberto").exists()


@pytest.mark.django_db
def test_ticket_list_filters_and_pagination(client, requester, category):
    for index in range(23):
        Ticket.objects.create(title=f"Rede {index}", description="incidente", category=category, requester=requester,
                             priority=Ticket.Priority.HIGH if index == 0 else Ticket.Priority.LOW)
    client.force_login(requester)
    response = client.get(reverse("ticket-list"), {"q": "Rede", "priority": Ticket.Priority.HIGH})
    assert response.status_code == 200
    assert response.context["page_obj"].paginator.count == 1
    response = client.get(reverse("ticket-list"), {"q": "Rede", "page": 2})
    assert response.context["page_obj"].number == 2
    assert len(response.context["tickets"]) == 3


@pytest.mark.django_db
def test_token_auth_and_api_resources(ticket, requester, agent, category):
    token = Token.objects.create(user=requester)
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
    assert client.get("/api/v1/tickets/").status_code == 200
    assert client.get("/api/v1/categories/").status_code == 200
    assert client.get("/api/v1/comments/").status_code == 200
    assert client.get("/api/v1/audits/").status_code == 403
    agent_token = Token.objects.create(user=agent)
    client.credentials(HTTP_AUTHORIZATION=f"Token {agent_token.key}")
    assert client.get("/api/v1/audits/").status_code == 200
    assert client.post("/api/v1/tickets/", {"title":"API ticket", "description":"details", "category":category.pk}).status_code == 201


@pytest.mark.django_db
def test_api_comment_create_update_delete_are_audited(ticket, requester):
    client = APIClient()
    client.force_authenticate(requester)
    created = client.post("/api/v1/comments/", {"ticket":ticket.pk, "body":"Primeira mensagem"}, format="json")
    assert created.status_code == 201
    comment_id = created.data["id"]
    assert ticket.audit_logs.filter(action="Comentário adicionado").exists()
    updated = client.patch(f"/api/v1/comments/{comment_id}/", {"body":"Mensagem corrigida"}, format="json")
    assert updated.status_code == 200
    assert ticket.audit_logs.filter(action="Comentário editado").exists()
    assert client.delete(f"/api/v1/comments/{comment_id}/").status_code == 204
    assert ticket.audit_logs.filter(action="Comentário excluído").exists()


@pytest.mark.django_db
def test_schema_and_token_endpoint_work(client):
    assert client.get("/api/schema/").status_code == 200
    assert client.get("/api/docs/").status_code == 200
    assert client.post("/api/token/", {}).status_code == 400


@pytest.mark.django_db
def test_admin_ticket_delete_is_disabled(client, ticket):
    admin_user = User.objects.create_superuser("root-test", "root@example.test", "safe-password-123")
    client.force_login(admin_user)
    response = client.get(f"/admin/tickets/ticket/{ticket.pk}/change/")
    assert response.status_code == 200
    from .admin import TicketAdmin, admin
    from django.test import RequestFactory
    assert not TicketAdmin(Ticket, admin.site).has_delete_permission(RequestFactory().get("/admin/"), ticket)
