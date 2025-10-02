from django.urls import path
from . import views

app_name = 'adminpanel'

urlpatterns = [
    path('adminLogin/', views.admin_login, name='admin_login'),
    path('adminSetting/', views.admin_setting, name='admin_setting'),
    path('dashboard/', views.admin_dashboard, name='admin_dashboard'), 
    path('officeUsage/', views.office_usage, name='office_usage'), 
    path('adminReports/', views.admin_reports, name='admin_reports'), 
    path('adminCosts./', views.admin_costs, name='admin_costs'),
    path('carbonEmission/', views.carbon_emission, name='carbon_emission'),
    path('createOffice/', views.create_office, name='create_office'),
    path('editOffice/<int:id>/', views.edit_office, name='edit_office'),
]
