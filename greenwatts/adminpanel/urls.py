from django.urls import path
from . import views

app_name = 'adminpanel'

urlpatterns = [
    path('adminLogin/', views.admin_login, name='admin_login'),
    path('adminSetting/', views.admin_setting, name='admin_setting'),
    path('dashboard/', views.admin_dashboard, name='admin_dashboard'), 
    path('officeUsage/', views.office_usage, name='office_usage'), 
]
