from rest_framework import serializers
from ..models import RegistroCliente

class RegistroClienteSerializer(serializers.ModelSerializer):
    class Meta:
        model = RegistroCliente
        fields = '__all__'