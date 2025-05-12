# auth/serializers.py
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework import serializers
from .models import ventapollos

class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    def validate(self, attrs):
        data = super().validate(attrs)
        user = self.user

        # Agrega el nombre del primer grupo (rol) si existe
        groups = user.groups.values_list('name', flat=True)
        data['role'] = list(groups) if groups else ['sin_rol']

        return data

class VentapollosSerializer(serializers.ModelSerializer):
    class Meta:
        model = ventapollos
        fields = '__all__'
        read_only_fields = ('id', 'create_date', 'update_date')
