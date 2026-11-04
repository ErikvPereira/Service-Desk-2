from django.contrib.auth import views as auth_views
from django.urls import path
from . import views

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("login/", views.ServiceDeskLoginView.as_view(), name="login"),
    path("signup/", views.signup, name="signup"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("tickets/", views.ticket_list, name="ticket-list"),
    path("my-tickets/", views.my_ticket_list, name="my-ticket-list"),
    path("tickets/new/", views.ticket_create, name="ticket-create"),
    path("tickets/<int:pk>/", views.ticket_detail, name="ticket-detail"),
]
