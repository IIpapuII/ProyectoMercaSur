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
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q
from django.db.models.functions import TruncDate
from django.shortcuts import render
import datetime

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
                # Guardar una sola vez y capturar la instancia
                cliente = serializer.save()
                
                if cliente.creado_desde_fisico == True:
                    mensaje = 'Cliente registrado exitosamente de forma local'
                    print("Cliente Creado localmente de forma exitosa")
                else:
                    try:
                        resultado = crearClienteICG(cliente)
                        if resultado == 'ok':
                            mensaje = 'Cliente registrado exitosamente en ICG'
                        else:
                            mensaje = f'Cliente creado localmente, pero hubo un error en ICG: {resultado}'
                    except Exception as e:
                        print(f"Error al crear cliente en ICG: {e}")
                        mensaje = f'Cliente creado localmente, pero falló la sincronización con ICG: {str(e)}'
                
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
    
@login_required
def dashboard_clientes(request):
    """
    Vista que obtiene varias métricas de RegistroCliente filtradas por rango de fechas
    (si se proporcionan) y las envía al template para graficarlas con Chart.js y mostrar KPIs adicionales.
    """

    # 1. LECTURA DE PARÁMETROS GET PARA FILTRAR POR FECHA
    #    - Se esperan en formato 'YYYY-MM-DD'
    start_date_str = request.GET.get('start_date')
    end_date_str   = request.GET.get('end_date')

    hoy = timezone.now().date()

    try:
        if start_date_str:
            start_date = datetime.datetime.strptime(start_date_str, '%Y-%m-%d').date()
        else:
            raise ValueError
        if end_date_str:
            end_date = datetime.datetime.strptime(end_date_str, '%Y-%m-%d').date()
        else:
            raise ValueError
        if start_date > end_date:
            raise ValueError
    except (ValueError, TypeError):
        # Si no vienen o son inválidos, usamos por defecto últimos 30 días
        end_date   = hoy
        start_date = hoy - datetime.timedelta(days=29)

    # Para mantener los valores en el formulario de filtro
    start_date_input = start_date.strftime('%Y-%m-%d')
    end_date_input   = end_date.strftime('%Y-%m-%d')

    # 2. QUERYSERVICE BASE FILTRADO POR EL RANGO SOBRE 'fecha_registro'
    base_qs = RegistroCliente.objects.filter(
        fecha_registro__date__gte=start_date,
        fecha_registro__date__lte=end_date
    )

    # 3. MÉTRICAS GENERALES SOBRE EL RANGO
    total_clients     = base_qs.count()
    created_icg       = base_qs.filter(creadoICG=True).count()
    updated_clients   = base_qs.filter(Actualizado=True).count()
    pending_clients   = base_qs.filter(
        creadoICG=False,
        Actualizado=False
    ).count()

    # 4. MÉTRICA “ICG + FIRMA” (creadoICG=True y firma_base64 no vacía)
    icg_con_firma = base_qs.filter(
        creadoICG=True
    ).exclude(
        Q(firma_base64='') | Q(firma_base64__isnull=True)
    ).count()

    # 5. SERIE TEMPORAL DIARIA (creadosICG, actualizados, ICG+FIRMA) DENTRO DEL RANGO
    qs_diaria = (
        base_qs
        .annotate(fecha=TruncDate('fecha_registro'))
        .values('fecha')
        .annotate(
            creados_icg  = Count('id', filter=Q(creadoICG=True)),
            actualizados = Count('id', filter=Q(Actualizado=True)),
            icg_firma    = Count('id', filter=Q(creadoICG=True) & ~Q(firma_base64='') & Q(firma_base64__isnull=False)),
            total        = Count('id'),
        )
        .order_by('fecha')
    )
    fechas_list       = [entry['fecha'].strftime('%Y-%m-%d') for entry in qs_diaria]
    creados_icg_list  = [entry['creados_icg'] for entry in qs_diaria]
    actualizados_list = [entry['actualizados'] for entry in qs_diaria]
    icg_firma_list    = [entry['icg_firma'] for entry in qs_diaria]

    # 6. DISTRIBUCIÓN POR TIPOCLIENTE (bar chart) DENTRO DEL RANGO
    qs_tipo = (
        base_qs
        .values('tipocliente')
        .annotate(count=Count('id'))
        .order_by('tipocliente')
    )
    tipos       = [entry['tipocliente'] or 'Sin tipo' for entry in qs_tipo]
    tipo_counts = [entry['count'] for entry in qs_tipo]

    # 7. CONTEO DE PREFERENCIAS DE CONTACTO (pie chart) DENTRO DEL RANGO
    pref_email     = base_qs.filter(preferencias_email=True).count()
    pref_whatsapp  = base_qs.filter(preferencias_whatsapp=True).count()
    pref_sms       = base_qs.filter(preferencias_sms=True).count()
    pref_redes     = base_qs.filter(preferencias_redes_sociales=True).count()
    pref_llamada   = base_qs.filter(preferencias_llamada=True).count()
    pref_ninguna   = base_qs.filter(preferencias_ninguna=True).count()

    # 8. NUEVAS MÉTRICAS SOLICITADAS DENTRO DEL RANGO
    clientes_formato_fisico = base_qs.filter(creado_desde_fisico=True).count()
    clientes_desde_admin    = base_qs.filter(creado_desde_admin=True).count()
    clientes_sin_cod        = base_qs.filter(codcliente__isnull=True).count()
    clientes_icg_sin_ip     = base_qs.filter(
        codcliente__isnull=False,
        ip_usuario__isnull=True
    ).count()
    client_no_fidelizados   = base_qs.filter(
        fidelizacion=False,
        tipocliente='Cliente',
        creadoICG=True
    ).count()

    # Listados para tablas de detalle
    clientes_sin_cod_list = base_qs.filter(codcliente__isnull=True).values(
        'id', 'primer_nombre', 'primer_apellido', 'numero_documento'
    )
    clientes_icg_sin_ip_list = base_qs.filter(
        codcliente__isnull=False, ip_usuario__isnull=True
    ).values('id', 'primer_nombre', 'primer_apellido', 'codcliente', 'numero_documento')

    # 9. DISTRIBUCIÓN POR PUNTO DE COMPRA (bar chart) DENTRO DEL RANGO
    qs_punto = (
        base_qs
        .values('punto_compra')
        .annotate(count=Count('id'))
        .order_by('punto_compra')
    )
    puntos_labels = [entry['punto_compra'] or 'Sin punto' for entry in qs_punto]
    puntos_counts = [entry['count'] for entry in qs_punto]

    # 10. CONSTRUCCIÓN DEL CONTEXTO
    context = {
        # Rango de fechas para el formulario
        'start_date_input':        start_date_input,
        'end_date_input':          end_date_input,

        # Métricas generales
        'total_clients':           total_clients,
        'created_icg':             created_icg,
        'updated_clients':         updated_clients,
        'pending_clients':         pending_clients,
        'icg_con_firma':           icg_con_firma,

        # Serie diaria (listas JSON)
        'fechas_json':             json.dumps(fechas_list),
        'creados_icg_json':        json.dumps(creados_icg_list),
        'actualizados_json':       json.dumps(actualizados_list),
        'icg_firma_json':          json.dumps(icg_firma_list),

        # Distribución Tipocliente
        'tipos_json':              json.dumps(tipos),
        'tipo_counts_json':        json.dumps(tipo_counts),

        # Preferencias
        'pref_email':              pref_email,
        'pref_whatsapp':           pref_whatsapp,
        'pref_sms':                pref_sms,
        'pref_redes':              pref_redes,
        'pref_llamada':            pref_llamada,
        'pref_ninguna':            pref_ninguna,

        # Nuevas métricas
        'clientes_formato_fisico': clientes_formato_fisico,
        'clientes_desde_admin':    clientes_desde_admin,
        'clientes_sin_cod':        clientes_sin_cod,
        'clientes_icg_sin_ip':     clientes_icg_sin_ip,
        'client_no_fidelizados':   client_no_fidelizados,

        # Listados para tablas
        'clientes_sin_cod_list':   list(clientes_sin_cod_list),
        'clientes_icg_sin_ip_list':list(clientes_icg_sin_ip_list),

        # Distribución Punto de Compra
        'puntos_json':             json.dumps(puntos_labels),
        'puntos_counts_json':      json.dumps(puntos_counts),
    }

    return render(request, 'dashboard_clientes.html', context)