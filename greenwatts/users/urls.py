from django.urls import path
from . import views

app_name = 'users'

urlpatterns = [
    path('', views.index, name='index'),
    path('verify-otp/', views.verify_otp, name='verify_otp'),
    path('resend-otp/', views.resend_otp, name='resend_otp'),
    path('dashboard/', views.dashboard, name='dashboard'),
    path('notifications/', views.notifications, name='notifications'),
    path('office-usage/', views.office_usage, name='office_usage'),
    path('user-reports/', views.user_reports, name='user_reports'),
    path('user-energy-cost/', views.user_energy_cost, name='user_energy_cost'),
    path('user-emmision/', views.user_emmision, name='user_emmision'),
    path('user-emission/', views.user_emmision, name='user_emission'),
    path('export-user-reports/', views.export_user_reports, name='export_user_reports'),
    path('get-user-days/', views.get_user_days, name='get_user_days'),
    path('get-user-weeks/', views.get_user_weeks, name='get_user_weeks'),
    path('logout/', views.logout, name='logout'),
]
