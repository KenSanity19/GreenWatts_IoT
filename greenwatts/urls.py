from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.http import HttpResponse
from django.views.generic import RedirectView

def favicon_view(request):
    return HttpResponse(status=204)  # No content

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('greenwatts.users.urls', namespace='users')),
    path('adminpanel/', include('greenwatts.adminpanel.urls', namespace='adminpanel')),
    path('', include('greenwatts.sensors.urls')),
    path('favicon.ico', favicon_view),
]

# Serve static files in production
if not settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
