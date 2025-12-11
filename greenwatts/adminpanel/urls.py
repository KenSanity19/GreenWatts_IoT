from django.urls import path
from . import views

app_name = 'adminpanel'

urlpatterns = [
    path('adminLogin/', views.admin_login, name='admin_login'),
    path('adminSetting/', views.admin_setting, name='admin_setting'),
    path('send-notification/', views.send_notification, name='send_notification'),
    path('dashboard/', views.admin_dashboard, name='admin_dashboard'), 
    path('officeUsage/', views.office_usage, name='office_usage'), 
    path('adminReports/', views.admin_reports, name='admin_reports'), 
    path('adminCosts./', views.admin_costs, name='admin_costs'),
    path('carbonEmission/', views.carbon_emission, name='carbon_emission'),
    path('createOffice/', views.create_office, name='create_office'),
    path('editOffice/<int:id>/', views.edit_office, name='edit_office'),
    path('createDevice/', views.create_device, name='create_device'),
    path('editDevice/<int:id>/', views.edit_device, name='edit_device'),
    path('saveThresholds/', views.save_thresholds, name='save_thresholds'),
    path('thresholdHistory/', views.threshold_history, name='threshold_history'),
    path('get-days/', views.get_days, name='get_days'),
    path('get_weeks/', views.get_weeks, name='get_weeks'),
    path('export-reports/', views.export_reports, name='export_reports'),
]
