from django.urls import path
from . import views

urlpatterns = [
    path('', views.index, name='sensors_home'),
]
