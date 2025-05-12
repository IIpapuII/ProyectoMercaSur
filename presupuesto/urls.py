from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from django.urls import path
from .views import CustomTokenObtainPairView, VentaPollosCreateAPIView, VentaPollosListAPIView


urlpatterns = [
    path('api/token/', CustomTokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('api/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('api/consecion-pollos/', VentaPollosCreateAPIView.as_view(), name='venta_pollos_create'),
    path('api/consecion-pollos/list/', VentaPollosListAPIView.as_view(), name='venta_pollos_list'),
]
