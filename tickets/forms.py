from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import UserCreationForm
from .models import Comment, Ticket
from .services import is_staff_member


class TicketCreateForm(forms.ModelForm):
    class Meta:
        model = Ticket
        fields = ("title", "description", "category", "priority")
        widgets = {"description": forms.Textarea(attrs={"rows": 6, "placeholder": "Descreva o impacto, contexto e o que já foi tentado."})}


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
