from django.urls import path
from django.conf import settings
from django.conf.urls.static import static
from .views import binnacle_dashboard, sugerencias_binnacle
urlpatterns = [
    path('api/sugerencias-binnacle/', sugerencias_binnacle, name='sugerencias_binnacle'),
]
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)