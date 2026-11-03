from rest_framework import serializers
from .models import AuditLog, Category, Comment, Ticket
from .services import audit, is_staff_member, update_ticket


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ("id", "name", "active")


class CommentSerializer(serializers.ModelSerializer):
    author_name = serializers.CharField(source="author.get_full_name", read_only=True)

    class Meta:
        model = Comment
        fields = ("id", "ticket", "author", "author_name", "body", "internal", "created_at")
        read_only_fields = ("author", "created_at")

    def validate_internal(self, value):
        if value and not is_staff_member(self.context["request"].user):
            raise serializers.ValidationError("Somente agentes podem criar notas internas.")
        return value

    def validate_ticket(self, value):
        from .services import visible_tickets
        if not visible_tickets(self.context["request"].user).filter(pk=value.pk).exists():
            raise serializers.ValidationError("Você não tem acesso a este chamado.")
        return value

    def create(self, validated_data):
        return Comment.objects.create(author=self.context["request"].user, **validated_data)


class TicketSerializer(serializers.ModelSerializer):
    requester_name = serializers.CharField(source="requester.get_full_name", read_only=True)
    assignee_name = serializers.CharField(source="assignee.get_full_name", read_only=True)

    class Meta:
        model = Ticket
        fields = ("id", "number", "title", "description", "category", "requester", "requester_name", "assignee", "assignee_name", "priority", "status", "created_at", "updated_at", "assigned_at", "first_response_at", "resolved_at", "closed_at")
        read_only_fields = ("number", "requester", "created_at", "updated_at", "assigned_at", "first_response_at", "resolved_at", "closed_at")

    def create(self, validated_data):
        ticket = Ticket.objects.create(requester=self.context["request"].user, **validated_data)
        audit(ticket, self.context["request"].user, "Chamado criado")
        return ticket

    def validate(self, attrs):
        if self.instance is None:
            if attrs.get("status", Ticket.Status.OPEN) != Ticket.Status.OPEN:
                raise serializers.ValidationError({"status": "Todo chamado deve ser aberto com status Aberto."})
            if attrs.get("assignee"):
                raise serializers.ValidationError({"assignee": "A atribuição deve ser realizada após a abertura."})
        return attrs

    def update(self, instance, validated_data):
        return update_ticket(instance, self.context["request"].user, **validated_data)


class AuditSerializer(serializers.ModelSerializer):
    actor_name = serializers.CharField(source="actor.get_full_name", read_only=True)
    class Meta:
        model = AuditLog
        fields = ("id", "ticket", "actor", "actor_name", "action", "field", "previous_value", "new_value", "created_at")
