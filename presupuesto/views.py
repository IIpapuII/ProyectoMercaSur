from rest_framework_simplejwt.views import TokenObtainPairView
from .serializers import CustomTokenObtainPairSerializer, VentapollosSerializer
from rest_framework import generics, permissions
from rest_framework.filters import OrderingFilter
from django_filters.rest_framework import DjangoFilterBackend
from .models import ventapollos
from rest_framework_simplejwt.authentication import JWTAuthentication

class CustomTokenObtainPairView(TokenObtainPairView):
    serializer_class = CustomTokenObtainPairSerializer

class VentaPollosCreateAPIView(generics.CreateAPIView):
    queryset = ventapollos.objects.all()
    serializer_class = VentapollosSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = [permissions.IsAuthenticated]

class VentaPollosListAPIView(generics.ListAPIView):
    serializer_class = VentapollosSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, OrderingFilter]
    ordering_fields = ['fecha', 'ubicacion']
    ordering = ['-fecha']

    def get_queryset(self):
        queryset = ventapollos.objects.all()
        fecha_inicio = self.request.query_params.get('fecha_inicio')
        fecha_fin = self.request.query_params.get('fecha_fin')
        ubicacion = self.request.query_params.get('ubicacion')

        if fecha_inicio and fecha_fin:
            queryset = queryset.filter(fecha__range=[fecha_inicio, fecha_fin])
        
        if ubicacion:
            queryset = queryset.filter(ubicacion__iexact=ubicacion)  # usa iexact para ignorar mayúsculas/minúsculas

        return queryset