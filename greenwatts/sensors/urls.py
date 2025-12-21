from django.urls import path
from . import views

urlpatterns = [
    path('api/sensor-data/', views.receive_sensor_data, name='receive_sensor_data'),
    path('api/wifi-networks/', views.get_wifi_networks, name='get_wifi_networks'),
    path('api/system-logs/', views.get_system_logs, name='get_system_logs'),
    path('api/weekly-analysis/', views.get_weekly_analysis, name='get_weekly_analysis'),
    path('api/generate-analysis/', views.generate_analysis, name='generate_analysis'),
]
