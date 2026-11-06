from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models.deletion import ProtectedError
from django.urls import reverse
from django.contrib.auth import authenticate
from django.test import RequestFactory
from django.utils import timezone
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
    with pytest.raises(PermissionDenied):
        update_ticket(ticket, requester, status=Ticket.Status.IN_PROGRESS)


@pytest.mark.django_db
def test_ticket_cannot_be_assigned_to_requester(ticket, agent, requester):
    with pytest.raises(ValidationError):
        update_ticket(ticket, agent, assignee=requester)
    ticket.refresh_from_db()
    assert ticket.assignee is None
    assert not ticket.audit_logs.exists()


@pytest.mark.django_db
def test_audited_ticket_cannot_be_deleted(ticket, requester):
    AuditLog.objects.create(ticket=ticket, actor=requester, action="Chamado criado")
    with pytest.raises(ProtectedError):
        ticket.delete()
    assert Ticket.objects.filter(pk=ticket.pk).exists()


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
def test_anonymous_users_are_redirected_from_private_pages(client):
    for route in ("dashboard", "ticket-list", "my-ticket-list", "ticket-create"):
        response = client.get(reverse(route))
        assert response.status_code == 302
        assert response.url.startswith(reverse("login"))


@pytest.mark.django_db
def test_requester_cannot_open_another_users_ticket_detail(client, requester, category):
    other = User.objects.create_user("outro-dono", password="safe-password-123")
    ticket = Ticket.objects.create(title="Restrito", description="x", category=category, requester=other)
    client.force_login(requester)
    assert client.get(reverse("ticket-detail", kwargs={"pk": ticket.pk})).status_code == 404


@pytest.mark.django_db
def test_dashboard_shows_real_counts_response_times_and_overdue_tickets(client, agent, requester, category):
    now = timezone.now()
    overdue_open = Ticket.objects.create(title="Aberto vencido", description="x", category=category, requester=requester)
    in_progress = Ticket.objects.create(title="Em atendimento", description="x", category=category, requester=requester, status=Ticket.Status.IN_PROGRESS)
    resolved = Ticket.objects.create(title="Resolvido", description="x", category=category, requester=requester, status=Ticket.Status.RESOLVED)
    Ticket.objects.filter(pk__in=(overdue_open.pk, in_progress.pk)).update(created_at=now - timedelta(days=4))
    Ticket.objects.filter(pk=resolved.pk).update(
        created_at=now - timedelta(hours=5),
        first_response_at=now - timedelta(hours=4),
        resolved_at=now,
    )
    client.force_login(agent)
    response = client.get(reverse("dashboard"))
    assert response.status_code == 200
    assert response.context["counts"][Ticket.Status.OPEN] == 1
    assert response.context["counts"][Ticket.Status.IN_PROGRESS] == 1
    assert response.context["counts"][Ticket.Status.RESOLVED] == 1
    assert response.context["overdue"] == 2
    assert response.context["first_response"] == timedelta(hours=1)
    assert response.context["resolution"] == timedelta(hours=5)


@pytest.mark.django_db
def test_ticket_list_applies_status_category_and_assignee_filters(client, agent, requester, category):
    second_category = Category.objects.create(name="Financeiro")
    match = Ticket.objects.create(
        title="Correspondente", description="x", category=category, requester=requester,
        assignee=agent, status=Ticket.Status.IN_PROGRESS,
    )
    Ticket.objects.create(
        title="Outra categoria", description="x", category=second_category, requester=requester,
        assignee=agent, status=Ticket.Status.IN_PROGRESS,
    )
    Ticket.objects.create(
        title="Outro responsável", description="x", category=category, requester=requester,
        status=Ticket.Status.IN_PROGRESS,
    )
    client.force_login(agent)
    response = client.get(reverse("ticket-list"), {
        "status": Ticket.Status.IN_PROGRESS,
        "category": category.pk,
        "assignee": agent.pk,
    })
    assert response.status_code == 200
    assert [item.pk for item in response.context["tickets"]] == [match.pk]


@pytest.mark.django_db
def test_logout_clears_the_authenticated_session(client, requester):
    client.force_login(requester)
    response = client.post(reverse("logout"))
    assert response.status_code == 302
    assert "_auth_user_id" not in client.session


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
    with pytest.raises(ValidationError):
        AuditLog.objects.filter(pk=audit.pk).delete()
    with pytest.raises(ValidationError):
        AuditLog.objects.filter(pk=audit.pk).update(action="Alterado")


@pytest.mark.django_db
def test_login_and_inactive_user(client, requester):
    response = client.post(reverse("login"), {"username": requester.username, "password": "safe-password-123"})
    assert response.status_code == 302
    requester.is_active = False
    requester.save()
    request = RequestFactory().post(reverse("login"))
    assert authenticate(request=request, username=requester.username, password="safe-password-123") is None


@pytest.mark.django_db
def test_first_signup_creates_admin_and_closes_public_signup(client):
    response = client.post(reverse("signup"), {
        "username": "novo", "password1": "A-safe-password-123!", "password2": "A-safe-password-123!",
    })
    user = User.objects.get(username="novo")
    assert response.status_code == 302
    assert user.profile.role == Profile.Role.ADMIN
    assert user.is_staff
    assert int(client.session["_auth_user_id"]) == user.pk
    client.logout()
    assert client.get(reverse("signup")).status_code == 302
    denied = client.post(reverse("signup"), {
        "username": "nao-autorizado", "password1": "A-safe-password-123!", "password2": "A-safe-password-123!",
    })
    assert denied.status_code == 302
    assert not User.objects.filter(username="nao-autorizado").exists()


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
    AuditLog.objects.create(ticket=ticket, actor=agent, action="Nota interna editada", field="comment", previous_value="Segredo anterior", new_value="Nota privada")
    client.force_login(requester)
    response = client.get(reverse("ticket-detail", kwargs={"pk": ticket.pk}))
    assert "Segredo anterior" not in response.content.decode()
    assert "Nota privada" not in response.content.decode()
    internal.body = "Texto editado"
    internal.save()
    AuditLog.objects.create(ticket=ticket, actor=agent, action="Comentário editado", field="comment", previous_value="Nota privada", new_value=internal.body)
    assert ticket.audit_logs.filter(action="Comentário editado").exists()


@pytest.mark.django_db
def test_requester_comment_is_public_even_if_internal_flag_is_submitted(client, ticket, requester):
    client.force_login(requester)
    response = client.post(reverse("ticket-detail", kwargs={"pk": ticket.pk}), {
        "comment-body": "Atualização pública",
        "comment-internal": "on",
        "add_comment": "",
    })
    comment = ticket.comments.get()
    assert response.status_code == 302
    assert comment.body == "Atualização pública"
    assert comment.internal is False
    assert ticket.audit_logs.get().action == "Comentário adicionado"


@pytest.mark.django_db
def test_agent_can_add_internal_comment_and_update_ticket_from_detail(client, ticket, agent, category):
    client.force_login(agent)
    response = client.post(reverse("ticket-detail", kwargs={"pk": ticket.pk}), {
        "comment-body": "Nota para a equipe",
        "comment-internal": "on",
        "add_comment": "",
    })
    comment = ticket.comments.get()
    assert response.status_code == 302
    assert comment.internal is True
    assert ticket.audit_logs.filter(action="Comentário interno adicionado").exists()

    response = client.post(reverse("ticket-detail", kwargs={"pk": ticket.pk}), {
        "update-category": category.pk,
        "update-priority": Ticket.Priority.HIGH,
        "update-status": Ticket.Status.IN_PROGRESS,
        "update-assignee": agent.pk,
        "update_ticket": "",
    })
    ticket.refresh_from_db()
    assert response.status_code == 302
    assert ticket.priority == Ticket.Priority.HIGH
    assert ticket.status == Ticket.Status.IN_PROGRESS
    assert ticket.assignee == agent
    assert ticket.assigned_at is not None
    assert ticket.first_response_at is not None
    assert ticket.audit_logs.filter(action="Campo atualizado", field="priority").exists()


@pytest.mark.django_db
def test_agent_invalid_status_transition_keeps_ticket_unchanged(client, ticket, agent):
    client.force_login(agent)
    response = client.post(reverse("ticket-detail", kwargs={"pk": ticket.pk}), {
        "update-category": ticket.category_id,
        "update-priority": ticket.priority,
        "update-status": Ticket.Status.RESOLVED,
        "update-assignee": "",
        "update_ticket": "",
    })
    ticket.refresh_from_db()
    assert response.status_code == 200
    assert "status" in response.context["update_form"].errors
    assert ticket.status == Ticket.Status.OPEN
    assert not ticket.audit_logs.exists()


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
def test_api_requester_can_create_ticket_and_cannot_change_it(ticket, requester, category):
    client = APIClient()
    client.force_authenticate(requester)
    created = client.post("/api/v1/tickets/", {
        "title": "Solicitação pela API",
        "description": "Detalhes da solicitação",
        "category": category.pk,
        "priority": Ticket.Priority.MEDIUM,
    }, format="json")
    assert created.status_code == 201
    created_ticket = Ticket.objects.get(pk=created.data["id"])
    assert created_ticket.requester == requester
    assert created_ticket.audit_logs.get().action == "Chamado criado"

    denied = client.patch(f"/api/v1/tickets/{ticket.pk}/", {"priority": Ticket.Priority.HIGH}, format="json")
    assert denied.status_code == 403
    ticket.refresh_from_db()
    assert ticket.priority == Ticket.Priority.MEDIUM


@pytest.mark.django_db
def test_agent_can_update_ticket_through_api_and_records_audit(ticket, agent):
    client = APIClient()
    client.force_authenticate(agent)
    response = client.patch(f"/api/v1/tickets/{ticket.pk}/", {
        "status": Ticket.Status.IN_PROGRESS,
        "assignee": agent.pk,
        "priority": Ticket.Priority.HIGH,
    }, format="json")
    ticket.refresh_from_db()
    assert response.status_code == 200
    assert ticket.status == Ticket.Status.IN_PROGRESS
    assert ticket.assignee == agent
    assert ticket.priority == Ticket.Priority.HIGH
    assert ticket.assigned_at is not None
    assert ticket.first_response_at is not None
    assert ticket.audit_logs.count() == 3


@pytest.mark.django_db
def test_api_ticket_filters_search_and_pagination(requester, category):
    for index in range(23):
        Ticket.objects.create(
            title=f"Incidente {index}", description="rede", category=category,
            requester=requester,
            priority=Ticket.Priority.HIGH if index == 0 else Ticket.Priority.LOW,
            status=Ticket.Status.IN_PROGRESS if index == 0 else Ticket.Status.OPEN,
        )
    client = APIClient()
    client.force_authenticate(requester)
    filtered = client.get("/api/v1/tickets/?status=in_progress&priority=high&search=Incidente%200")
    assert filtered.status_code == 200
    assert filtered.data["count"] == 1
    assert filtered.data["results"][0]["title"] == "Incidente 0"

    second_page = client.get("/api/v1/tickets/?ordering=-created_at&page=2")
    assert second_page.status_code == 200
    assert second_page.data["count"] == 23
    assert len(second_page.data["results"]) == 3


@pytest.mark.django_db
def test_service_admin_can_manage_requesters_but_cannot_escalate_admins(db):
    from django.contrib import admin
    from .admin import ProfileAdmin, UserAdmin

    manager = User.objects.create_user("service-admin", password="safe-password-123")
    manager.profile.role = Profile.Role.ADMIN
    manager.profile.save()
    member = User.objects.create_user("team-member", password="safe-password-123")
    another_admin = User.objects.create_user("another-admin", password="safe-password-123")
    another_admin.profile.role = Profile.Role.ADMIN
    another_admin.profile.save()
    root = User.objects.create_superuser("root-admin", "root@example.test", "safe-password-123")

    request = RequestFactory().get("/admin/")
    request.user = manager
    user_admin = UserAdmin(User, admin.site)
    profile_admin = ProfileAdmin(Profile, admin.site)
    assert user_admin.has_module_permission(request)
    assert user_admin.has_change_permission(request, member)
    assert not user_admin.has_change_permission(request, another_admin)
    assert user_admin.has_delete_permission(request, member)
    assert not user_admin.has_delete_permission(request, another_admin)
    role_choices = dict(profile_admin.get_form(request, member.profile).base_fields["role"].choices)
    assert Profile.Role.ADMIN not in role_choices
    assert not profile_admin.has_change_permission(request, another_admin.profile)

    request.user = root
    root_choices = dict(profile_admin.get_form(request, member.profile).base_fields["role"].choices)
    assert Profile.Role.ADMIN in root_choices
    assert user_admin.has_change_permission(request, another_admin)


@pytest.mark.django_db
def test_api_comment_validation_and_author_restrictions(ticket, requester, agent, category):
    other = User.objects.create_user("outro-api", password="safe-password-123")
    foreign_ticket = Ticket.objects.create(title="Chamado de outra pessoa", description="x", category=category, requester=other)
    staff_comment = ticket.comments.create(author=agent, body="Comentário da equipe")
    client = APIClient()
    client.force_authenticate(requester)

    private = client.post("/api/v1/comments/", {
        "ticket": ticket.pk, "body": "Nota interna", "internal": True,
    }, format="json")
    inaccessible = client.post("/api/v1/comments/", {
        "ticket": foreign_ticket.pk, "body": "Comentário alheio",
    }, format="json")
    assert private.status_code == 400
    assert inaccessible.status_code == 400
    assert client.patch(f"/api/v1/comments/{staff_comment.pk}/", {"body": "Alterado"}, format="json").status_code == 403
    assert client.delete(f"/api/v1/comments/{staff_comment.pk}/").status_code == 403
    staff_comment.refresh_from_db()
    assert staff_comment.body == "Comentário da equipe"


@pytest.mark.django_db
def test_categories_api_is_read_only_and_excludes_inactive_categories(category):
    inactive = Category.objects.create(name="Arquivada", active=False)
    client = APIClient()
    user = User.objects.create_user("category-reader", password="safe-password-123")
    client.force_authenticate(user)
    response = client.get("/api/v1/categories/")
    assert response.status_code == 200
    active_ids = {row["id"] for row in response.data["results"]}
    assert category.pk in active_ids
    assert inactive.pk not in active_ids
    assert client.post("/api/v1/categories/", {"name": "Nova"}).status_code == 405
    assert client.delete(f"/api/v1/categories/{inactive.pk}/").status_code == 405


@pytest.mark.django_db
def test_health_endpoint_returns_database_status(client):
    response = client.get(reverse("health"))
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "ok"}


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
    assert client.get("/api/schema/").status_code == 401
    assert client.get("/api/docs/").status_code == 401
    assert client.post("/api/token/", {}).status_code == 400
    admin_user = User.objects.create_superuser("schema-admin", "schema@example.test", "safe-password-123")
    client.force_login(admin_user)
    assert client.get("/api/schema/").status_code == 200
    assert client.get("/api/docs/").status_code == 200


@pytest.mark.django_db
def test_api_tokens_expire_and_can_be_reissued(requester):
    from datetime import timedelta
    from django.utils import timezone

    api_client = APIClient()
    token = Token.objects.create(user=requester)
    token.created = timezone.now() - timedelta(days=31)
    token.save(update_fields=("created",))
    api_client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
    assert api_client.get("/api/v1/tickets/").status_code == 401
    assert not Token.objects.filter(pk=token.pk).exists()
    api_client.credentials()
    response = api_client.post("/api/token/", {"username": "solicitante", "password": "safe-password-123"})
    assert response.status_code == 200
    assert response.json()["token"]
    assert response.json()["expires_at"]


@pytest.mark.django_db
def test_ticket_cannot_be_deleted_through_api(ticket):
    admin_user = User.objects.create_superuser("delete-admin", "delete@example.test", "safe-password-123")
    client = APIClient()
    client.force_authenticate(admin_user)
    assert client.delete(f"/api/v1/tickets/{ticket.pk}/").status_code == 403
    assert Ticket.objects.filter(pk=ticket.pk).exists()


@pytest.mark.django_db
def test_admin_ticket_delete_is_disabled(client, ticket):
    admin_user = User.objects.create_superuser("root-test", "root@example.test", "safe-password-123")
    client.force_login(admin_user)
    response = client.get(f"/admin/tickets/ticket/{ticket.pk}/change/")
    assert response.status_code == 200
    from .admin import TicketAdmin, admin
    from django.test import RequestFactory
    assert not TicketAdmin(Ticket, admin.site).has_delete_permission(RequestFactory().get("/admin/"), ticket)
