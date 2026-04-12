from django.urls import path
from . import views

app_name = 'piquano_ms365'

urlpatterns = [
    path('', views.status, name='status'),
    path('connect/', views.connect, name='connect'),
    path('callback', views.callback, name='callback'),
    path('callback/', views.callback),
    path('disconnect/', views.disconnect, name='disconnect'),
    path('notify/', views.notify, name='notify'),
    path('notify', views.notify),
]
