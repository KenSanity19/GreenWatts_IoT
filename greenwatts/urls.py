from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('greenwatts.users.urls', namespace='users')),
    path('adminpanel/', include('greenwatts.adminpanel.urls', namespace='adminpanel')),
    
]
