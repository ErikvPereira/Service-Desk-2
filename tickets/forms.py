from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import UserCreationForm
from .models import Comment, Ticket
from .services import is_staff_member


class TicketCreateForm(forms.ModelForm):
    class Meta:
        model = Ticket
        fields = ("title", "description", "category", "priority")
        widgets = {
            "title": forms.TextInput(attrs={"placeholder": "Ex.: Não consigo acessar o e-mail corporativo"}),
            "description": forms.Textarea(attrs={"rows": 7, "placeholder": "Explique o que aconteceu, o impacto e o que você já tentou fazer."}),
        }
        help_texts = {
            "title": "Use um resumo claro para facilitar a identificação do problema.",
            "description": "Inclua detalhes relevantes, como sistema afetado, mensagens exibidas e urgência.",
            "category": "Escolha a área que melhor representa sua solicitação.",
            "priority": "Use a prioridade que melhor representa o impacto no seu trabalho.",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["category"].empty_label = "Selecione uma categoria"


class TicketUpdateForm(forms.ModelForm):
    class Meta:
        model = Ticket
        fields = ("category", "priority", "status", "assignee")

    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, **kwargs)
        if not is_staff_member(user):
            for field in self.fields.values():
                field.disabled = True


class CommentForm(forms.ModelForm):
    class Meta:
        model = Comment
        fields = ("body", "internal")
        widgets = {"body": forms.Textarea(attrs={"rows": 3, "placeholder": "Adicione uma atualização…"})}

    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, **kwargs)
        if not is_staff_member(user):
            self.fields.pop("internal")


class SignUpForm(UserCreationForm):
    class Meta:
        model = get_user_model()
        fields = ("username", "first_name", "last_name", "email")
