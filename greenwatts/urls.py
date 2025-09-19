from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),
    path('sensors/', include('sensors.urls')),
    path('users/', include('users.urls')),
    path('adminpanel/', include('adminpanel.urls')),
]
