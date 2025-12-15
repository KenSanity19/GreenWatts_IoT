from django.urls import path
from . import views

urlpatterns = [
    path('api/sensor-data/', views.receive_sensor_data, name='receive_sensor_data'),
    path('api/wifi-networks/', views.get_wifi_networks, name='get_wifi_networks'),
]
