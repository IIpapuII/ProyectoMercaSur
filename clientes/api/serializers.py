from rest_framework import serializers
from ..models import RegistroCliente, ZonaPermitida, barrio

class RegistroClienteSerializer(serializers.ModelSerializer):
    class Meta:
        model = RegistroCliente
        fields = '__all__'

class ClienteGetSerializer(serializers.ModelSerializer):
    class Meta:
        model = RegistroCliente
        fields = ['primer_apellido',
                  'segundo_apellido',
                  'primer_nombre',
                  'segundo_nombre',
                  'numero_documento',
                  'fecha_nacimiento',
                ]

class ZonaPermitidaSerializer(serializers.ModelSerializer):
    """
    Serializador para el modelo ZonaPermitida.
    Convierte instancias del modelo a JSON y viceversa (si es necesario).
    """
    class Meta:
        model = ZonaPermitida
        fields = [
            'id',         
            'latitude',
            'longitude',
            'max_distance',
        ]

class barrioSerializer(serializers.ModelSerializer):
    """
    Serializador para el modelo barrio.
    Convierte instancias del modelo a JSON y viceversa (si es necesario).
    """
    class Meta:
        model = barrio
        fields = [
            'id',
            'nombre',
        ]

class ClienteICGSerializer(serializers.Serializer):
    codcliente = serializers.IntegerField()
    NumeroDocumento = serializers.CharField(source='NumeroDocumento')
    PrimerNombre = serializers.CharField()
    SegundoNombre = serializers.CharField()
    PrimerApellido = serializers.CharField()
    SegundoApellido = serializers.CharField()
    FechaNacimiento = serializers.DateField(source='FECHANACIMIENTO')