from django.urls import path
from .views import RegistroFormularioAPIView

urlpatterns = [
    path('clientes/', RegistroFormularioAPIView.as_view(), name='registro-formulario'),
    path('clientes/', RegistroFormularioAPIView.as_view(), name='registro-formulario-detalle'),
    path('clientes/<int:numero_documento>/', RegistroFormularioAPIView.as_view(), name='registro-formulario-actualizar'),
]
