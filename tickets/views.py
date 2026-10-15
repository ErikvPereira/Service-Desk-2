from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.db.models import Avg, Count, DurationField, ExpressionWrapper, F, Q
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
    form = SignUpForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        login(request, user)
        messages.success(request, "Usuário criado com sucesso.")
        return redirect("dashboard")
    return render(request, "registration/signup.html", {"form": form})


@login_required
def dashboard(request):
    tickets = visible_tickets(request.user)
    counts = {value: tickets.filter(status=value).count() for value, _label in Ticket.Status.choices}
    priority_counts = tickets.values("priority").annotate(total=Count("id")).order_by("priority")
    resolution = tickets.filter(resolved_at__isnull=False).aggregate(value=Avg(ExpressionWrapper(F("resolved_at") - F("created_at"), output_field=DurationField())))["value"]
    return render(request, "tickets/dashboard.html", {"counts": counts, "priority_counts": priority_counts, "resolution": resolution, "recent": tickets[:6]})


@login_required
def ticket_list(request):
    tickets = _filters(request, visible_tickets(request.user))
    page_obj = Paginator(tickets, 20).get_page(request.GET.get("page"))
    return render(request, "tickets/ticket_list.html", {
        "tickets": page_obj, "page_obj": page_obj, "statuses": Ticket.Status.choices, "priorities": Ticket.Priority.choices,
        "categories": Category.objects.filter(active=True),
        "agents": Profile.objects.filter(role__in=[Profile.Role.ADMIN, Profile.Role.AGENT], user__is_active=True).select_related("user"),
    })


@login_required
def ticket_create(request):
    form = TicketCreateForm(request.POST or None)
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
    if not can_manage:
        comments = comments.filter(internal=False)
    return render(request, "tickets/ticket_detail.html", {
        "ticket": ticket, "comment_form": comment_form, "update_form": update_form,
        "comments": comments, "audits": ticket.audit_logs.select_related("actor"), "can_manage": can_manage,
    })
