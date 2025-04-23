from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from .api.serializers import RegistroClienteSerializer, ZonaPermitidaSerializer
from django.shortcuts import get_object_or_404
from .models import RegistroCliente , ZonaPermitida
from rest_framework import generics, permissions

class RegistroFormularioAPIView(APIView):
    def post(self, request):
        documento = request.data.get('numero_documento')
        if not documento:
            return Response({'error': 'El campo "numero_documento" es obligatorio'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            instancia = RegistroCliente.objects.get(numero_documento=documento)
            # Si el cliente ya existe, actualizamos los datos (PUT)
            serializer = RegistroClienteSerializer(instancia, data=request.data)
            if serializer.is_valid():
                serializer.save()
                mensaje = 'Datos actualizados correctamente'
                return Response({'mensaje': mensaje}, status=status.HTTP_200_OK)
            else:
                return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        except RegistroCliente.DoesNotExist:
            # Si el cliente no existe, lo creamos (POST)
            serializer = RegistroClienteSerializer(data=request.data)
            if serializer.is_valid():
                serializer.save()
                mensaje = 'Cliente registrado exitosamente'
                return Response({'mensaje': mensaje}, status=status.HTTP_201_CREATED)
            else:
                return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    def get_object(self):
        return get_object_or_404(RegistroCliente, numero_documento=self.kwargs['numero_documento'])
    
    def put(self, request, numero_documento=None):
        print(f"Actualizando cliente con pk: {numero_documento}")
        try:
            cliente = self.get_object()
            serializer = RegistroClienteSerializer(cliente, data=request.data, partial=True)
            print(f"Datos recibidos para actualizar: {request.data}")
            if serializer.is_valid():
                serializer.save()
                return Response({'mensaje': 'Cliente actualizado correctamente'}, status=status.HTTP_200_OK)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        except RegistroCliente.DoesNotExist:
            return Response({'error': 'Cliente no encontrado'}, status=status.HTTP_404_NOT_FOUND)
    
    def get(self, request, *args, **kwargs):
        numero_documento = request.query_params.get('numero_documento')
        if not numero_documento:
            return Response({'error': 'Debe enviar el número de documento como parámetro'}, status=status.HTTP_400_BAD_REQUEST)

        cliente = RegistroCliente.objects.filter(numero_documento=numero_documento).first()
        if cliente:
            serializer = RegistroClienteSerializer(cliente)
            return Response({
                'existe': True,
                'cliente': serializer.data
            }, status=status.HTTP_200_OK)
        else:
            return Response({'existe': False}, status=status.HTTP_200_OK)


class ZonaPermitidaListView(generics.ListAPIView):
    """
    Vista de API para listar todas las Zonas Permitidas *activas*.
    """
    serializer_class = ZonaPermitidaSerializer
    permission_classes = [permissions.AllowAny] 
    def get_queryset(self):
        return ZonaPermitida.objects.filter(activa=True)
