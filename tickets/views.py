from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.contrib.auth import views as auth_views
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.db import connection, transaction
from django.db.models import Avg, Count, DurationField, ExpressionWrapper, F, Q
from django.utils import timezone
from datetime import timedelta
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from .forms import CommentForm, SignUpForm, TicketCreateForm, TicketUpdateForm
from .models import AuditLog, Category, Profile, Ticket
from .services import audit, is_staff_member, update_ticket, visible_tickets


def _filters(request, queryset):
    search = request.GET.get("q", "").strip()
    if search:
        queryset = queryset.filter(Q(number__icontains=search) | Q(title__icontains=search) | Q(description__icontains=search))
    for field in ("status", "priority", "category", "assignee"):
        if value := request.GET.get(field):
            queryset = queryset.filter(**{field: value})
    ordering = request.GET.get("ordering", "-created_at")
    if ordering.lstrip("-") in {"created_at", "priority", "updated_at", "status"}:
        queryset = queryset.order_by(ordering)
    return queryset


def signup(request):
    if request.user.is_authenticated:
        return redirect("dashboard")
    if get_user_model().objects.exists():
        messages.error(request, "O cadastro público está fechado. Solicite uma conta ao administrador do Service Desk.")
        return redirect("login")
    form = SignUpForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            # Serializa os cadastros iniciais para que somente a primeira conta
            # receba o perfil de administrador, inclusive em acessos simultâneos.
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_advisory_xact_lock(%s)", [7342026])
            first_user = not get_user_model().objects.exists()
            user = form.save() if first_user else None
            if user is not None:
                user.profile.role = Profile.Role.ADMIN
                user.profile.save()
        if user is None:
            messages.error(request, "O cadastro público foi fechado. Solicite uma conta ao administrador do Service Desk.")
            return redirect("login")
        login(request, user, backend="django.contrib.auth.backends.ModelBackend")
        messages.success(
            request,
            "Administrador inicial criado com sucesso."
            if first_user else "Usuário criado com sucesso.",
        )
        return redirect("dashboard")
    return render(request, "registration/signup.html", {
        "form": form,
        "first_user": not get_user_model().objects.exists(),
    })


class ServiceDeskLoginView(auth_views.LoginView):
    template_name = "registration/login.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["signup_open"] = not get_user_model().objects.exists()
        return context


@login_required
def dashboard(request):
    tickets = visible_tickets(request.user)
    counts = {value: tickets.filter(status=value).count() for value, _label in Ticket.Status.choices}
    priority_counts = tickets.values("priority").annotate(total=Count("id")).order_by("priority")
    resolved = tickets.filter(resolved_at__isnull=False)
    resolution = resolved.aggregate(value=Avg(ExpressionWrapper(F("resolved_at") - F("created_at"), output_field=DurationField())))["value"]
    first_response = tickets.filter(first_response_at__isnull=False).aggregate(value=Avg(ExpressionWrapper(F("first_response_at") - F("created_at"), output_field=DurationField())))["value"]
    sla_hours = int(__import__("os").getenv("SERVICEDESK_SLA_HOURS", "72"))
    overdue = tickets.filter(status__in=[Ticket.Status.OPEN, Ticket.Status.IN_PROGRESS, Ticket.Status.WAITING], created_at__lt=timezone.now() - timedelta(hours=sla_hours)).count()
    return render(request, "tickets/dashboard.html", {"counts": counts, "priority_counts": priority_counts, "resolution": resolution, "first_response": first_response, "overdue": overdue, "sla_hours": sla_hours, "recent": tickets[:6]})


@login_required
def ticket_list(request):
    visible = visible_tickets(request.user)
    tickets = _filters(request, visible)
    return _render_ticket_list(request, tickets, visible, "Chamados", "Todos os chamados", "ticket-list")


@login_required
def my_ticket_list(request):
    visible = visible_tickets(request.user).filter(requester=request.user)
    tickets = _filters(request, visible)
    return _render_ticket_list(request, tickets, visible, "Meus chamados", "Meus chamados", "my-ticket-list")


def _render_ticket_list(request, tickets, visible_tickets_queryset, page_title, table_title, list_url_name):
    page_obj = Paginator(tickets, 20).get_page(request.GET.get("page"))
    ticket_summary = visible_tickets_queryset.aggregate(
        total=Count("id"),
        open=Count("id", filter=Q(status=Ticket.Status.OPEN)),
        in_progress=Count("id", filter=Q(status=Ticket.Status.IN_PROGRESS)),
        waiting=Count("id", filter=Q(status=Ticket.Status.WAITING)),
        closed=Count("id", filter=Q(status=Ticket.Status.CLOSED)),
    )
    return render(request, "tickets/ticket_list.html", {
        "tickets": page_obj, "page_obj": page_obj, "statuses": Ticket.Status.choices, "priorities": Ticket.Priority.choices,
        "categories": Category.objects.filter(active=True),
        "agents": Profile.objects.filter(role__in=[Profile.Role.ADMIN, Profile.Role.AGENT], user__is_active=True).select_related("user"),
        "page_title": page_title, "table_title": table_title, "ticket_summary": ticket_summary, "list_url_name": list_url_name,
    })


@login_required
def ticket_create(request):
    form = TicketCreateForm(request.POST if request.method == "POST" else None)
    if request.method == "POST" and form.is_valid():
        ticket = form.save(commit=False)
        ticket.requester = request.user
        ticket.save()
        audit(ticket, request.user, "Chamado criado")
        messages.success(request, f"Chamado {ticket.number} aberto com sucesso.")
        return redirect("ticket-detail", pk=ticket.pk)
    return render(request, "tickets/ticket_form.html", {"form": form})


@login_required
def ticket_detail(request, pk):
    ticket = get_object_or_404(visible_tickets(request.user), pk=pk)
    can_manage = is_staff_member(request.user)
    comment_form = CommentForm(request.POST or None, user=request.user, prefix="comment")
    update_form = TicketUpdateForm(request.POST or None, instance=ticket, user=request.user, prefix="update")
    if request.method == "POST":
        if "add_comment" in request.POST and comment_form.is_valid():
            comment = comment_form.save(commit=False)
            comment.ticket, comment.author = ticket, request.user
            comment.save()
            audit(ticket, request.user, "Comentário interno adicionado" if comment.internal else "Comentário adicionado")
            messages.success(request, "Atualização registrada.")
            return redirect("ticket-detail", pk=pk)
        if "update_ticket" in request.POST and can_manage and update_form.is_valid():
            try:
                cleaned = update_form.cleaned_data
                update_ticket(ticket, request.user, **cleaned)
                messages.success(request, "Chamado atualizado.")
                return redirect("ticket-detail", pk=pk)
            except (ValidationError, PermissionDenied) as exc:
                update_form.add_error(None, exc)
    comments = ticket.comments.select_related("author")
    audits = ticket.audit_logs.select_related("actor")
    if not can_manage:
        comments = comments.filter(internal=False)
        audits = (audits.exclude(action__startswith="Nota interna")
                  .exclude(action="Comentário interno adicionado")
                  .exclude(action__in=("Comentário editado", "Comentário excluído")))
    return render(request, "tickets/ticket_detail.html", {
        "ticket": ticket, "comment_form": comment_form, "update_form": update_form,
        "comments": comments, "audits": audits, "can_manage": can_manage,
    })
