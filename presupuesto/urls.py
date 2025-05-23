from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from django.urls import path
from .views import CustomTokenObtainPairView, VentaPollosCreateAPIView, VentaPollosListAPIView, vista_presupuesto_por_categoria, vista_consultar_presupuesto, vista_reporte_cumplimiento


urlpatterns = [
    path('api/token/', CustomTokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('api/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('api/consecion-pollos/', VentaPollosCreateAPIView.as_view(), name='venta_pollos_create'),
    path('api/consecion-pollos/list/', VentaPollosListAPIView.as_view(), name='venta_pollos_list'),
    path('presupuesto/calcular/', vista_presupuesto_por_categoria, name='vista_presupuesto_calcular'),
    path('presupuesto/consultar/', vista_consultar_presupuesto, name='vista_presupuesto_consultar'),
    path('presupuesto/reporte-cumplimiento/', vista_reporte_cumplimiento, name='vista_reporte_cumplimiento'),
]
