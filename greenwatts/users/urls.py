from django.urls import path
from . import views

app_name = 'users'

urlpatterns = [
    path('', views.index, name='index'),
    path('dashboard/', views.dashboard, name='dashboard'),
    path('office-usage/', views.office_usage, name='office_usage'),
    path('user-reports/', views.user_reports, name='user_reports'),
    path('user-energy-cost/', views.user_energy_cost, name='user_energy_cost'),
    path('user-emmision/', views.user_emmision, name='user_emmision'),
    path('export-user-reports/', views.export_user_reports, name='export_user_reports'),
    path('logout/', views.logout, name='logout'),
]
