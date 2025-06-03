from django.urls import path
from .views import RegistroFormularioAPIView, ZonaPermitidaListView, barrioListView, validar_codigo_acceso, dashboard_clientes

urlpatterns = [
    path('clientes/', RegistroFormularioAPIView.as_view(), name='registro-formulario'),
    path('clientes/', RegistroFormularioAPIView.as_view(), name='registro-formulario-detalle'),
    path('clientes/<int:numero_documento>/', RegistroFormularioAPIView.as_view(), name='registro-formulario-actualizar'),
    path('zonas-permitidas/', ZonaPermitidaListView.as_view(), name='zonas-permitidas'),
    path('barrios/', barrioListView.as_view(), name='barrios'),
    path('validar-codigo-acceso/',validar_codigo_acceso,name='CodigoAcceso'),
    path('dashboard-clientes/', dashboard_clientes, name='dashboard-clientes'),
]
