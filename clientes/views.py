from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from .api.serializers import RegistroClienteSerializer, ZonaPermitidaSerializer, barrioSerializer, ClienteGetSerializer
from django.shortcuts import get_object_or_404
from .models import RegistroCliente , ZonaPermitida, barrio
from automatizaciones.models import CorreoEnviado
from rest_framework import generics, permissions
from service.clientICG import ConsultarClienteICG, crearClienteICG, actualizarClienteICG
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
import json
import os
from django.conf import settings
from .correo import enviar_correo, enviar_correo_html
from django.http import HttpResponse
from django.utils import timezone

class RegistroFormularioAPIView(APIView):
    permission_classes = [permissions.AllowAny] 
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
            print(request.data)
            if serializer.is_valid():
                serializer.save()
                cliente = serializer.save()
                if cliente.creado_desde_fisico == True:
                    mensaje = 'Cliente registrado exitosamente de forma local'
                    print("Cliente Creado  localmente de forma exitosa")
                else:
                    crearClienteICG(cliente)
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
                instancia = serializer.save()
                actualizarClienteICG(instancia)
                return Response({'mensaje': 'Cliente actualizado correctamente'}, status=status.HTTP_200_OK)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        except RegistroCliente.DoesNotExist:
            return Response({'error': 'Cliente no encontrado'}, status=status.HTTP_404_NOT_FOUND)
    
    def get(self, request, *args, **kwargs):
        numero_documento = request.query_params.get('numero_documento')
        if not numero_documento:
            return Response({'error': 'Debe enviar el número de documento como parámetro'}, status=status.HTTP_400_BAD_REQUEST)
        ConsultarClienteICG(numero_documento)
        cliente = RegistroCliente.objects.filter(numero_documento=numero_documento).first()
        if cliente:
            serializer = ClienteGetSerializer(cliente)
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

class barrioListView(generics.ListAPIView):
    serializer_class = barrioSerializer
    permission_classes = [permissions.AllowAny]
    def get_queryset(self):
        return barrio.objects.all()



@csrf_exempt
@require_POST
def validar_codigo_acceso(request):
    from .models import CodigoTemporal
    """
    Valida el código de acceso enviado desde el frontend comparándolo
    con el código activo generado por el modelo CodigoTemporal y su fecha de vencimiento.
    Espera una petición POST con un cuerpo JSON: {"codigo": "codigo_ingresado"}
    Retorna JSON: {"valido": true} o {"valido": false} con un posible mensaje de error.
    """
    try:
        # Cargar el cuerpo de la petición como JSON
        data = json.loads(request.body)
        codigo_ingresado = data.get('codigo')

        if not codigo_ingresado:
            # Si no se envió 'codigo' en el JSON
            return JsonResponse({'valido': False, 'error': 'Código no proporcionado'}, status=400) # Bad Request

        try:
            # Buscar un código en la base de datos que coincida con el ingresado
            codigo_temporal = CodigoTemporal.objects.get(codigo=codigo_ingresado)
            print(f"Código encontrado en la base de datos: {codigo_temporal.codigo}, Vencimiento: {codigo_temporal.fecha_vencimiento}")

            # Verificar si el código ha vencido
            if codigo_temporal.fecha_vencimiento is not None and timezone.now() > codigo_temporal.fecha_vencimiento:
                return JsonResponse({'valido': False, 'error': 'El código ha expirado'})
            else:
                # Si no ha vencido, se considera válido
                return JsonResponse({'valido': True})

        except CodigoTemporal.DoesNotExist:
            # Si no se encuentra ningún código con el valor ingresado
            return JsonResponse({'valido': False, 'error': 'Código inválido'})

    except json.JSONDecodeError:
        # Error si el cuerpo de la petición no es JSON válido
        return JsonResponse({'valido': False, 'error': 'Cuerpo de la petición inválido (no es JSON)'}, status=400)
    except Exception as e:
        # Capturar cualquier otro error inesperado
        print(f"Error inesperado en validar_codigo_acceso: {e}") # Loguear el error
        return JsonResponse({'valido': False, 'error': 'Error interno del servidor'}, status=500) # Internal Server Error
    
