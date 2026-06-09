from django.urls import path
from . import views

app_name = "pq_privacy"

urlpatterns = [
    path("acknowledge/", views.privacy_acknowledge, name="acknowledge"),
]
