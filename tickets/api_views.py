from rest_framework import viewsets
from rest_framework.exceptions import PermissionDenied
from .models import AuditLog, Category, Comment, Ticket
from .serializers import AuditSerializer, CategorySerializer, CommentSerializer, TicketSerializer
from .services import audit, is_staff_member, visible_tickets


class TicketViewSet(viewsets.ModelViewSet):
    serializer_class = TicketSerializer
    filterset_fields = ("status", "priority", "category", "assignee", "requester")
    search_fields = ("number", "title", "description")
    ordering_fields = ("created_at", "updated_at", "priority", "status")

    def get_queryset(self):
        return visible_tickets(self.request.user)

    def perform_update(self, serializer):
        if not is_staff_member(self.request.user):
            raise PermissionDenied("Somente agentes podem atualizar chamados.")
        serializer.save()

    def perform_destroy(self, instance):
        if not self.request.user.is_superuser:
            raise PermissionDenied("Chamados não podem ser excluídos, exceto por administradores.")
        instance.delete()


class CommentViewSet(viewsets.ModelViewSet):
    serializer_class = CommentSerializer
    filterset_fields = ("ticket", "internal")

    def get_queryset(self):
        tickets = visible_tickets(self.request.user)
        queryset = Comment.objects.filter(ticket__in=tickets).select_related("author")
        return queryset if is_staff_member(self.request.user) else queryset.filter(internal=False)

    def perform_update(self, serializer):
        if serializer.instance.author != self.request.user and not self.request.user.is_superuser:
            raise PermissionDenied("Você só pode editar seus próprios comentários.")
        serializer.save()

    def perform_create(self, serializer):
        comment = serializer.save()
        audit(comment.ticket, self.request.user, "Comentário interno adicionado" if comment.internal else "Comentário adicionado")

    def perform_destroy(self, instance):
        if instance.author != self.request.user and not self.request.user.is_superuser:
            raise PermissionDenied("Você só pode excluir seus próprios comentários.")
        ticket = instance.ticket
        instance.delete()
        audit(ticket, self.request.user, "Comentário excluído")


class CategoryViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Category.objects.filter(active=True)
    serializer_class = CategorySerializer


class AuditViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = AuditSerializer
    filterset_fields = ("ticket", "action", "field")
    def get_queryset(self):
        if not is_staff_member(self.request.user):
            raise PermissionDenied("O histórico de auditoria é restrito à equipe de atendimento.")
        return AuditLog.objects.filter(ticket__in=visible_tickets(self.request.user)).select_related("actor", "ticket")
