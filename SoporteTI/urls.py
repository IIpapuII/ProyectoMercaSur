from django.urls import path
from django.conf import settings
from django.conf.urls.static import static
from .views import binnacle_dashboard
urlpatterns = [
    path('SoporteTI/binnacle-dashboard/', binnacle_dashboard, name='binnacle_dashboard'),
]
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)