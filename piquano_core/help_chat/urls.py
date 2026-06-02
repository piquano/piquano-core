from django.urls import path
from . import views

app_name = "pq_help_chat"

urlpatterns = [
    path("ask/", views.help_chat_proxy, name="ask"),
]
