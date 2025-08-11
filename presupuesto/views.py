import calendar
import json
from django.http import JsonResponse
from rest_framework_simplejwt.views import TokenObtainPairView
from .serializers import CustomTokenObtainPairSerializer, VentapollosSerializer
from rest_framework import generics, permissions
from rest_framework.filters import OrderingFilter
from django_filters.rest_framework import DjangoFilterBackend
from .models import VentaDiariaReal, ventapollos, CategoriaVenta
from rest_framework_simplejwt.authentication import JWTAuthentication
from django.utils.safestring import mark_safe
from django.shortcuts import render
from django.contrib import messages # Para mostrar mensajes al usuario
from .forms import FiltroCumplimientoForm, SedeAñoMesForm, PresupuestoCategoriaFormSet, FiltroRangoFechasForm
from .models import Sede, CategoriaVenta, PresupuestoMensualCategoria, PresupuestoDiarioCategoria
from .utils import calcular_presupuesto_con_porcentajes_dinamicos, obtener_clase_semaforo
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from django.db.models import Sum, F
from appMercaSur.decorators import smart_jwt_login_required
from django.utils.timezone import now
from datetime import date, datetime, timedelta

from django.views.decorators.csrf import csrf_exempt

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

# --- Vista Para Cálculo ---
@smart_jwt_login_required
def vista_presupuesto_por_categoria(request):
    categorias_queryset = CategoriaVenta.objects.all().order_by('nombre')

    if not categorias_queryset.exists():
         messages.error(request, "Error: No hay categorías de venta/presupuesto definidas en el sistema.")
         # Aquí podrías renderizar un template simple de error o redirigir
         return render(request, 'error_configuracion.html', {'mensaje': "No hay categorías definidas."})


    sede_form = SedeAñoMesForm(request.POST or None, prefix='main')
    
    # Para el formset, necesitamos construirlo con la cantidad correcta de formularios
    # tanto para GET como para POST si hay errores de validación y se re-renderiza.
    if request.method == 'POST':
        presupuesto_formset = PresupuestoCategoriaFormSet(request.POST, prefix='categorias')
    else: # GET request
        # Crear un formset vacío con un formulario por cada categoría para la carga inicial
        presupuesto_formset = PresupuestoCategoriaFormSet(
            initial=[{} for _ in categorias_queryset], 
            prefix='categorias'
        )

    # Combinar categorías con sus respectivos formularios para el template
    # Esto es importante para que en el template se puedan mostrar los labels correctos
    categorias_and_forms_for_template = list(zip(categorias_queryset, presupuesto_formset.forms))
    if not categorias_and_forms_for_template and categorias_queryset.exists() and not presupuesto_formset.forms:
        # Fallback si presupuesto_formset.forms está vacío pero debería tener forms (ej. GET inicial sin 'initial' en formset)
        # Esto puede suceder si la instanciación del formset para GET no crea los forms explícitamente.
        # Re-instanciar con 'extra' o 'initial' adecuado es clave.
        # El 'initial' en la definición del formset para GET ahora debería manejar esto.
        pass


    resultados_diarios = None
    totales_finales_categoria = None
    gran_total_componentes = None
    contexto_presupuesto_input = None

    if request.method == 'POST':
        print("Procesando POST para cálculo...")
        if sede_form.is_valid() and presupuesto_formset.is_valid():
            print("Formularios Válidos para cálculo.")
            sede = sede_form.cleaned_data['sede']
            anio = sede_form.cleaned_data['anio']
            mes = sede_form.cleaned_data['mes']

            presupuestos_input = {}
            input_valid = True
            
            for i, form_cat in enumerate(presupuesto_formset.cleaned_data): # Iterar sobre cleaned_data
                try:
                    # Necesitamos asegurar que el índice 'i' corresponda a categorias_queryset[i]
                    # Esto asume que presupuesto_formset.cleaned_data mantiene el orden y longitud
                    if i < len(categorias_queryset):
                        categoria_obj = categorias_queryset[i]
                        presupuesto_valor_str = form_cat.get('presupuesto') # form_cat es un dict aquí
                        presupuesto_valor = Decimal(presupuesto_valor_str) if presupuesto_valor_str else Decimal('0.00')

                        if presupuesto_valor < 0:
                            # Para añadir error al form específico, necesitaríamos iterar sobre forms, no cleaned_data
                            # presupuesto_formset.forms[i].add_error('presupuesto', 'El presupuesto no puede ser negativo.')
                            messages.error(request, f"El presupuesto para {categoria_obj.nombre} no puede ser negativo.")
                            input_valid = False
                        else:
                            presupuestos_input[categoria_obj.nombre] = presupuesto_valor
                            PresupuestoMensualCategoria.objects.update_or_create(
                                sede=sede, categoria=categoria_obj, anio=anio, mes=mes,
                                defaults={'presupuesto_total_categoria': presupuesto_valor}
                            )
                    else: # Más forms en el formset que categorías, lo cual no debería pasar con extra=0
                        messages.error(request, "Discrepancia en el número de formularios y categorías.")
                        input_valid = False; break
                except IndexError:
                    messages.error(request, "Error de concordancia entre categorías y formularios del formset.")
                    input_valid = False; break
                except (InvalidOperation, TypeError, KeyError) as e: # KeyError si 'presupuesto' no está en form_cat
                    messages.error(request, f"Error en los datos de entrada para una categoría.")
                    input_valid = False; break
            
            if input_valid:
                print(f"Inputs recolectados: {presupuestos_input}")
                # Asegurarse de que 'total' (o el nombre de tu categoría global) esté en presupuestos_input si se espera
                # Si el error es "categoría 'total' no tiene porcentajes", y 'total' no está en presupuestos_input,
                # entonces el problema es que no se está enviando un presupuesto para 'total'.
                if not presupuestos_input: # Si no se recolectó ningún presupuesto válido
                    messages.warning(request, "No se ingresaron presupuestos para procesar.")
                else:
                    resultados_diarios, totales_finales_categoria, gran_total_componentes = \
                        calcular_presupuesto_con_porcentajes_dinamicos(anio, mes, presupuestos_input)

                    if resultados_diarios is not None:
                        messages.success(request, "Cálculo de presupuesto diario realizado y datos guardados con éxito.")
                        contexto_presupuesto_input = {
                            'sede_nombre': sede.nombre, 'anio': anio, 'mes': mes,
                            'categorias_nombres': sorted(list(presupuestos_input.keys())),
                            'presupuestos_input': presupuestos_input
                        }
                        # Guardar Resultados Diarios en BD
                        qs_mensuales = PresupuestoMensualCategoria.objects.filter(sede=sede, anio=anio, mes=mes)
                        PresupuestoDiarioCategoria.objects.filter(presupuesto_mensual__in=qs_mensuales).delete()
                        nuevos_diarios = []
                        for dia_data in resultados_diarios:
                            for cat_nombre, datos_cat_dia in dia_data['budgets_by_category'].items():
                                try:
                                    presup_mensual_cat_obj = qs_mensuales.get(categoria__nombre=cat_nombre)
                                    nuevos_diarios.append(PresupuestoDiarioCategoria(
                                        presupuesto_mensual=presup_mensual_cat_obj,
                                        fecha=dia_data['fecha'],
                                        dia_semana_nombre=dia_data['dia_semana_nombre'],
                                        porcentaje_dia_especifico=datos_cat_dia['porcentaje_usado'],
                                        presupuesto_calculado=datos_cat_dia['valor']
                                    ))
                                except PresupuestoMensualCategoria.DoesNotExist:
                                    print(f"Advertencia: No se encontró PresupuestoMensual para {sede.nombre}/{cat_nombre}/{mes}/{anio} al guardar diarios.")
                        if nuevos_diarios:
                            PresupuestoDiarioCategoria.objects.bulk_create(nuevos_diarios)
                            print(f"Guardados {len(nuevos_diarios)} registros diarios.")
                    else:
                        messages.error(request, "Falló el cálculo del presupuesto diario. Revise la configuración de porcentajes (¿suman 100%?, ¿están los 7 días para cada categoría activa?).")
        else: # Formularios principales no válidos
            print("Formularios Inválidos para cálculo (sede_form o presupuesto_formset).")
            messages.warning(request, "Por favor corrija los errores en el formulario de cálculo.")
            # Re-construir categorias_and_forms_for_template si hay errores para mostrar los forms de nuevo
            categorias_and_forms_for_template = list(zip(categorias_queryset, presupuesto_formset.forms))

    context = {
        'sede_form': sede_form,
        'presupuesto_formset': presupuesto_formset,
        'categorias_and_forms': categorias_and_forms_for_template,
        'resultados': resultados_diarios,
        'totales_finales_categoria': totales_finales_categoria,
        'gran_total_componentes': gran_total_componentes,
        'contexto_presupuesto_input': contexto_presupuesto_input,
    }
    return render(request, 'calcular_presupuesto.html', context) # Nueva plantilla


# --- Vista Para Consulta ---
@smart_jwt_login_required
def vista_consultar_presupuesto(request):
    filter_form = SedeAñoMesForm(request.GET or None, prefix='filter')
    
    resultados_diarios = None
    totales_finales_categoria = None
    gran_total_componentes = None
    contexto_presupuesto_input = None

    if filter_form.is_valid():
        sede = filter_form.cleaned_data['sede']
        anio = filter_form.cleaned_data['anio']
        mes = filter_form.cleaned_data['mes']
        print(f"Consultando para: Sede={sede}, Año={anio}, Mes={mes}")

        presupuestos_mensuales_guardados = PresupuestoMensualCategoria.objects.filter(
            sede=sede, anio=anio, mes=mes
        ).select_related('categoria').order_by('categoria__nombre')

        if not presupuestos_mensuales_guardados.exists():
            messages.info(request, f"No se encontraron datos de presupuesto guardados para {sede.nombre} en {mes}/{anio}.")
        else:
            input_presupuestos = {pm.categoria.nombre: pm.presupuesto_total_categoria for pm in presupuestos_mensuales_guardados}
            categorias_consultadas_nombres = sorted(list(input_presupuestos.keys()))
            
            contexto_presupuesto_input = {
                'sede_nombre': sede.nombre, 'anio': anio, 'mes': mes,
                'categorias_nombres': categorias_consultadas_nombres,
                'presupuestos_input': input_presupuestos
            }
            print(f"Contexto Input reconstruido: {contexto_presupuesto_input}")

            fechas_con_datos = PresupuestoDiarioCategoria.objects.filter(
                presupuesto_mensual__in=presupuestos_mensuales_guardados
            ).values_list('fecha', flat=True).distinct().order_by('fecha')

            if not fechas_con_datos:
                messages.warning(request, f"Presupuestos mensuales encontrados para {sede.nombre} en {mes}/{anio}, pero no hay datos diarios calculados asociados.")
            else:
                resultados_diarios_list = []
                totales_finales_categoria_dict = {cat_nombre: Decimal('0.00') for cat_nombre in categorias_consultadas_nombres}
                gran_total_componentes_val = Decimal('0.00')

                for fecha_dia in fechas_con_datos:
                    dia_data = {
                        'fecha': fecha_dia, 'dia_semana_nombre': '',
                        'budgets_by_category': {}, 'total_dia_componentes': Decimal('0.00')
                    }
                    registros_diarios_del_dia = PresupuestoDiarioCategoria.objects.filter(
                        presupuesto_mensual__in=presupuestos_mensuales_guardados, fecha=fecha_dia
                    ).select_related('presupuesto_mensual__categoria')

                    if registros_diarios_del_dia:
                         dia_data['dia_semana_nombre'] = registros_diarios_del_dia.first().dia_semana_nombre

                    for cat_nombre in categorias_consultadas_nombres:
                        registro_cat_dia = next((r for r in registros_diarios_del_dia if r.presupuesto_mensual.categoria.nombre == cat_nombre), None)
                        if registro_cat_dia:
                            valor = registro_cat_dia.presupuesto_calculado
                            pct_usado = registro_cat_dia.porcentaje_dia_especifico
                            dia_data['budgets_by_category'][cat_nombre] = {'valor': valor, 'porcentaje_usado': pct_usado}
                            totales_finales_categoria_dict[cat_nombre] += valor
                            if cat_nombre != "Total Sede": # Nombre exacto de tu categoría global
                                dia_data['total_dia_componentes'] += valor
                        else:
                            dia_data['budgets_by_category'][cat_nombre] = {'valor': Decimal('0.00'), 'porcentaje_usado': Decimal('0.00')}
                    
                    dia_data['total_dia_componentes'] = dia_data['total_dia_componentes'].quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
                    resultados_diarios_list.append(dia_data)
                    gran_total_componentes_val += dia_data['total_dia_componentes']
                
                for cat_n in totales_finales_categoria_dict:
                    totales_finales_categoria_dict[cat_n] = totales_finales_categoria_dict[cat_n].quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
                
                resultados_diarios = resultados_diarios_list
                totales_finales_categoria = totales_finales_categoria_dict
                gran_total_componentes = gran_total_componentes_val.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
                messages.success(request, f"Mostrando datos guardados para {sede.nombre} en {mes}/{anio}.")
    else:
        if request.GET and not filter_form.is_valid():
             messages.warning(request, "Por favor corrija los errores en el formulario de filtro.")

    context = {
        'filter_form': filter_form,
        'resultados': resultados_diarios,
        'totales_finales_categoria': totales_finales_categoria,
        'gran_total_componentes': gran_total_componentes,
        'contexto_presupuesto_input': contexto_presupuesto_input, # Contiene 'categorias_nombres'
    }
    return render(request, 'consultar_presupuesto.html', context) # Nueva plantilla

@smart_jwt_login_required
def vista_reporte_cumplimiento(request):
    filtro_form = FiltroCumplimientoForm(request.GET or None, user=request.user)
    datos_reporte = []
    resumen_mensual = None
    contexto_filtro = None
    resumen_por_categoria = []
    chart_labels, chart_data_ppto, chart_data_venta = [], [], []
    chart_labels_anual, chart_ppto_anual, chart_venta_anual, chart_cumplimiento_anual = [], [], [], []

    fecha_inicio = request.GET.get("fecha_inicio")
    fecha_fin = request.GET.get("fecha_fin")
    try:
        fecha_inicio = datetime.strptime(fecha_inicio, '%Y-%m-%d').date() if fecha_inicio else None
        fecha_fin = datetime.strptime(fecha_fin, '%Y-%m-%d').date() if fecha_fin else None
    except ValueError:
        fecha_inicio = None
        fecha_fin = None

    if filtro_form.is_valid():
        sede = filtro_form.cleaned_data['sede']
        categoria_seleccionada = filtro_form.cleaned_data['categoria']
        anio = filtro_form.cleaned_data['anio']
        mes = filtro_form.cleaned_data['mes']

        hoy = now().date()
        ultimo_dia = calendar.monthrange(anio, mes)[1]
        limite_fecha = hoy if hoy.month == mes and hoy.year == anio else date(anio, mes, ultimo_dia)

        contexto_filtro = {
            'sede_nombre': sede.nombre,
            'categoria_nombre': categoria_seleccionada.nombre,
            'anio': anio,
            'mes': mes
        }

        # Filtrar solo las categorías permitidas al usuario
        perfil = getattr(request.user, 'perfil', None)
        if perfil:
            todas_las_categorias = perfil.categorias_permitidas.all()
        else:
            todas_las_categorias = CategoriaVenta.objects.none()

        for cat_obj in todas_las_categorias:
            filtro_presupuesto = {
                'presupuesto_mensual__sede': sede,
                'presupuesto_mensual__categoria': cat_obj
            }
            filtro_venta = {
                'sede': sede,
                'categoria': cat_obj
            }

            if fecha_inicio:
                filtro_presupuesto['fecha__gte'] = fecha_inicio
                filtro_venta['fecha__gte'] = fecha_inicio
            if fecha_fin:
                filtro_presupuesto['fecha__lte'] = fecha_fin
                filtro_venta['fecha__lte'] = fecha_fin
            if not fecha_inicio and not fecha_fin:
                filtro_presupuesto['presupuesto_mensual__anio'] = anio
                filtro_presupuesto['presupuesto_mensual__mes'] = mes
                filtro_presupuesto['fecha__lte'] = limite_fecha

                filtro_venta['fecha__year'] = anio
                filtro_venta['fecha__month'] = mes
                filtro_venta['fecha__lte'] = limite_fecha

            presupuesto_total_cat = PresupuestoDiarioCategoria.objects.filter(**filtro_presupuesto).aggregate(
                total_presupuesto=Sum('presupuesto_calculado')
            )['total_presupuesto'] or Decimal('0.00')

            venta_total_cat = VentaDiariaReal.objects.filter(**filtro_venta).aggregate(
                total_venta=Sum('venta_real')
            )['total_venta'] or Decimal('0.00')

            diferencia_cat = venta_total_cat - presupuesto_total_cat
            cumplimiento_cat_pct = None
            if presupuesto_total_cat > 0:
                cumplimiento_cat_pct = (venta_total_cat / presupuesto_total_cat * Decimal('100')).quantize(Decimal('0.1'), rounding=ROUND_HALF_UP)

            if presupuesto_total_cat > 0:
                resumen_por_categoria.append({
                    'nombre_indicador': cat_obj.nombre,
                    'presupuesto_mes': presupuesto_total_cat,
                    'venta_mes': venta_total_cat,
                    'diferencia': diferencia_cat,
                    'cumplimiento_pct': cumplimiento_cat_pct,
                    'semaforo_clase': obtener_clase_semaforo(cumplimiento_cat_pct)
                })

        resumen_por_categoria = sorted(resumen_por_categoria, key=lambda x: x['presupuesto_mes'], reverse=True)

        # GRAFICA ANUAL PRESUPUESTO VS VENTA
        chart_labels_anual = ['Ene', 'Feb', 'Mar', 'Abr', 'May', 'Jun', 'Jul', 'Ago', 'Sep', 'Oct', 'Nov', 'Dic']
        chart_ppto_anual = []
        chart_venta_anual = []
        chart_cumplimiento_anual = []

        for m in range(1, 13):
            filtro_ppto_mensual = {
                'presupuesto_mensual__sede': sede,
                'presupuesto_mensual__categoria': categoria_seleccionada,
                'presupuesto_mensual__anio': anio,
                'presupuesto_mensual__mes': m
            }
            filtro_venta_mensual = {
                'sede': sede,
                'categoria': categoria_seleccionada,
                'fecha__year': anio,
                'fecha__month': m
            }

            if fecha_inicio:
                filtro_ppto_mensual['fecha__gte'] = fecha_inicio
                filtro_venta_mensual['fecha__gte'] = fecha_inicio
            if fecha_fin:
                filtro_ppto_mensual['fecha__lte'] = fecha_fin
                filtro_venta_mensual['fecha__lte'] = fecha_fin

            ppto_qs = PresupuestoDiarioCategoria.objects.filter(**filtro_ppto_mensual).aggregate(total_ppto=Sum('presupuesto_calculado'))
            total_ppto = ppto_qs['total_ppto'] or Decimal('0.00')

            total_venta = VentaDiariaReal.objects.filter(**filtro_venta_mensual).aggregate(total_venta=Sum('venta_real'))['total_venta'] or Decimal('0.00')

            chart_ppto_anual.append(float(total_ppto))
            chart_venta_anual.append(float(total_venta))
            if total_ppto > 0:
                chart_cumplimiento_anual.append(round((total_venta / total_ppto) * 100, 1))
            else:
                chart_cumplimiento_anual.append(0.0)

        # DETALLE DIARIO (YA EXISTENTE)
        presupuestos_diarios = PresupuestoDiarioCategoria.objects.filter(
            presupuesto_mensual__sede=sede,
            presupuesto_mensual__categoria=categoria_seleccionada,
            presupuesto_mensual__anio=anio,
            presupuesto_mensual__mes=mes
        ).order_by('fecha')

        if not presupuestos_diarios.exists():
            messages.info(request, f"No se encontraron presupuestos diarios para {categoria_seleccionada.nombre} en {sede.nombre} para {mes}/{anio}.")
        else:
            ventas_diarias_qs = VentaDiariaReal.objects.filter(
                sede=sede,
                categoria=categoria_seleccionada,
                fecha__year=anio,
                fecha__month=mes
            )
            ventas_map = {v.fecha: v for v in ventas_diarias_qs}

            total_ppto_mes_detalle = Decimal('0.00')
            total_venta_mes_detalle = Decimal('0.00')

            dias_semana_ordenados = ['Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado', 'Domingo']
            resumen_semanal_detalle = {
                dia: {'presupuesto': Decimal('0'), 'venta': Decimal('0')}
                for dia in dias_semana_ordenados
            }

            for ppto_dia in presupuestos_diarios:
                venta_obj = ventas_map.get(ppto_dia.fecha)
                if venta_obj:
                    venta_dia_real = venta_obj.venta_real
                    margen_sin_pos   = venta_obj.margen_sin_post_pct
                    margen_con_pos   = venta_obj.margen_con_post_pct
                else:
                    venta_dia_real = Decimal('0.00')
                    margen_sin_pos = Decimal('0.0')
                    margen_con_pos = Decimal('0.0')

                nombre_dia = ppto_dia.dia_semana_nombre
                if nombre_dia in resumen_semanal_detalle:
                    resumen_semanal_detalle[nombre_dia]['presupuesto'] += ppto_dia.presupuesto_calculado
                    resumen_semanal_detalle[nombre_dia]['venta'] += venta_dia_real

                diferencia = venta_dia_real - ppto_dia.presupuesto_calculado
                cumplimiento_pct_dia = None
                if ppto_dia.presupuesto_calculado > 0:
                    cumplimiento_pct_dia = (venta_dia_real / ppto_dia.presupuesto_calculado * Decimal('100')).quantize(Decimal('0.1'), rounding=ROUND_HALF_UP)
                fecha_aa = ppto_dia.fecha.replace(year=ppto_dia.fecha.year - 1)
                venta_aa_obj = VentaDiariaReal.objects.filter(
                    sede=sede,
                    categoria=categoria_seleccionada,
                    fecha=fecha_aa
                ).first()
                venta_anio_pasado = venta_aa_obj.venta_real if venta_aa_obj else Decimal('0.00')
                datos_reporte.append({
                    'fecha': ppto_dia.fecha,
                    'dia_semana': ppto_dia.dia_semana_nombre,
                    'presupuesto_diario': ppto_dia.presupuesto_calculado,
                    'venta_diaria': venta_dia_real,
                    'venta_anio_pasado': venta_anio_pasado,
                    'diferencia': diferencia,
                    'cumplimiento_pct': cumplimiento_pct_dia,
                    'semaforo_clase': obtener_clase_semaforo(cumplimiento_pct_dia),
                    'margen_sin_pos': margen_sin_pos,
                    'margen_con_pos': margen_con_pos
                })

                total_ppto_mes_detalle += ppto_dia.presupuesto_calculado
                total_venta_mes_detalle += venta_dia_real

            chart_labels = dias_semana_ordenados
            chart_data_ppto = [float(resumen_semanal_detalle[dia]['presupuesto']) for dia in dias_semana_ordenados]
            chart_data_venta = [float(resumen_semanal_detalle[dia]['venta']) for dia in dias_semana_ordenados]

            cumplimiento_total_mes_detalle = None
            if total_ppto_mes_detalle > 0:
                cumplimiento_total_mes_detalle = (total_venta_mes_detalle / total_ppto_mes_detalle * Decimal('100')).quantize(Decimal('0.1'), rounding=ROUND_HALF_UP)

            resumen_mensual = {
                'total_presupuesto': total_ppto_mes_detalle,
                'total_venta': total_venta_mes_detalle,
                'total_venta_anio_pasado': VentaDiariaReal.objects.filter(
                    sede=sede,
                    categoria=categoria_seleccionada,
                    fecha__year=anio - 1,
                    fecha__month=mes
                ).aggregate(total_venta=Sum('venta_real'))['total_venta'] or Decimal('0.00'),
                'total_diferencia': total_venta_mes_detalle - total_ppto_mes_detalle,
                'cumplimiento_pct': cumplimiento_total_mes_detalle,
                'semaforo_clase': obtener_clase_semaforo(cumplimiento_total_mes_detalle),
                'margen_sin_pos': ventas_diarias_qs.aggregate(Sum('margen_sin_post_pct'))['margen_sin_post_pct__sum'] or Decimal('0.0'),
                'margen_con_pos': ventas_diarias_qs.aggregate(Sum('margen_con_post_pct'))['margen_con_post_pct__sum'] or Decimal('0.0')
            }

            if not datos_reporte and presupuestos_diarios.exists():
                messages.info(request, f"Se encontraron presupuestos para {categoria_seleccionada.nombre}, pero no ventas para mostrar detalle diario.")

    context = {
        'filtro_form': filtro_form,
        'resumen_por_categoria': resumen_por_categoria,
        'datos_reporte': datos_reporte,
        'resumen_mensual': resumen_mensual,
        'contexto_filtro': contexto_filtro,
        'chart_labels': mark_safe(json.dumps(chart_labels)),
        'chart_data_ppto': mark_safe(json.dumps(chart_data_ppto)),
        'chart_data_venta': mark_safe(json.dumps(chart_data_venta)),
        'chart_labels_anual': mark_safe(json.dumps(chart_labels_anual)),
        'chart_ppto_anual': mark_safe(json.dumps(chart_ppto_anual)),
        'chart_venta_anual': mark_safe(json.dumps(chart_venta_anual)),
        'chart_cumplimiento_anual': mark_safe(json.dumps([float(v) for v in chart_cumplimiento_anual])),
        'fecha_inicio': fecha_inicio,
        'fecha_fin': fecha_fin,
        'is_administrativo': request.user.groups.filter(name='administrativos').exists()
    }
    return render(request, 'reporte_cumplimiento.html', context)

@csrf_exempt
@smart_jwt_login_required
def iniciar_sesion_django(request):
    user = request.user
    roles = list(user.groups.values_list('name', flat=True))

    role_redirects_vue = {
        'admin': '/admin-dashboard',
        'ventaspollos': '/concesion-pollos',
    }
    role_redirects_django = {
        'presupuesto': '/presupuesto/reporte-cumplimiento/',

        # Agrega otras rutas de Django aquí si es necesario
    }

    redirect_url = '/' 

    for role in roles:
        if role in role_redirects_django:
            redirect_url = role_redirects_django[role]
            break 
    
    if redirect_url == '/':
        for role in roles:
            if role in role_redirects_vue:
                redirect_url = role_redirects_vue[role]
                break

    return JsonResponse({
        'success': True,
        'message': 'Sesión de Django iniciada.',
        'redirect_url': redirect_url
    })

@smart_jwt_login_required
def dasboard_presupuesto(request):
    form = FiltroRangoFechasForm(request.GET or None, user=request.user)

    summary_table = []
    labels1, ppto_data, venta_data, cmp_data = [], [], [], []
    labels2, imp_act, imp_ant, dif_pct, cmp_ant_data = [], [], [], [], []

    if form.is_valid():
        fi = form.cleaned_data['fecha_inicio']
        ff = form.cleaned_data['fecha_fin']
        cat = form.cleaned_data['categoria']

        # Filtros base para el rango de fechas
        filtro_venta = {'fecha__range': (fi, ff)}
        filtro_presu = {'fecha__range': (fi, ff)}
        if cat:
            filtro_venta['categoria'] = cat
            filtro_presu['presupuesto_mensual__categoria'] = cat

        # Filtros para año anterior (mismo rango de días pero año anterior)
        fi_anterior = fi.replace(year=fi.year - 1) if fi else None
        ff_anterior = ff.replace(year=ff.year - 1) if ff else None
        filtro_venta_anterior = {'fecha__range': (fi_anterior, ff_anterior)} if fi_anterior and ff_anterior else {}
        if cat:
            filtro_venta_anterior['categoria'] = cat

        # Tabla resumen
        qs_ppto = PresupuestoDiarioCategoria.objects.filter(**filtro_presu) \
            .values(sede_nombre=F('presupuesto_mensual__sede__nombre')) \
            .annotate(total_ppto=Sum('presupuesto_calculado'))

        qs_venta = VentaDiariaReal.objects.filter(**filtro_venta) \
            .values(sede_nombre=F('sede__nombre')) \
            .annotate(total_venta=Sum('venta_real'))

        qs_venta_anterior = VentaDiariaReal.objects.filter(**filtro_venta_anterior) \
            .values(sede_nombre=F('sede__nombre')) \
            .annotate(total_venta=Sum('venta_real'))

        dict_ppto  = {r['sede_nombre']: r['total_ppto'] for r in qs_ppto}
        dict_venta = {r['sede_nombre']: r['total_venta'] for r in qs_venta}
        dict_venta_anterior = {r['sede_nombre']: r['total_venta'] for r in qs_venta_anterior}
        sedes = sorted(set(dict_ppto) | set(dict_venta))

        total_ppto_all = 0
        total_venta_all = 0
        total_venta_ant_all = 0

        for sede in sedes:
            p = dict_ppto.get(sede, 0) or 0
            v = dict_venta.get(sede, 0) or 0
            va = dict_venta_anterior.get(sede, 0) or 0
            ejec = round((v / p) * 100) if p else 0
            diff = v - p
            cmp_ant = round((v / va) * 100, 1) if va else 0.0

            summary_table.append({
                'sede': sede,
                'ppto': float(p),
                'venta': float(v),
                'ejec_pct': ejec,
                'diff': float(diff),
                'cmp_ant': cmp_ant,
                'venta_anterior': float(va),
            })

            total_ppto_all += p
            total_venta_all += v
            total_venta_ant_all += va

        # Fila de totales
        ejec_tot = round((total_venta_all / total_ppto_all) * 100) if total_ppto_all else 0
        cmp_ant_tot = round((total_venta_all / total_venta_ant_all) * 100, 1) if total_venta_ant_all else 0.0
        summary_table.append({
            'sede': 'Totales',
            'ppto': float(total_ppto_all),
            'venta': float(total_venta_all),
            'ejec_pct': ejec_tot,
            'diff': float(total_venta_all - total_ppto_all),
            'cmp_ant': cmp_ant_tot,
            'venta_anterior': float(total_venta_ant_all),
        })

        # Gráfico 1: Venta vs Presupuesto
        for row in summary_table[:-1]:
            labels1.append(row['sede'])
            ppto_data.append(row['ppto'])
            venta_data.append(row['venta'])
            cmp_data.append(row['ejec_pct'])
            cmp_ant_data.append(row['cmp_ant'])

        labels1.append('TOTAL')
        ppto_data.append(summary_table[-1]['ppto'])
        venta_data.append(summary_table[-1]['venta'])
        cmp_data.append(summary_table[-1]['ejec_pct'])
        cmp_ant_data.append(summary_table[-1]['cmp_ant'])

        # Gráfico 2: Mes actual vs año anterior (solo rango de fechas)
        for sede in sedes:
            ia = dict_venta.get(sede, 0) or 0
            ib = dict_venta_anterior.get(sede, 0) or 0
            labels2.append(sede)
            imp_act.append(float(ia))
            imp_ant.append(float(ib))
            dif_pct.append(float(round((ia / ib) * 100 - 100, 1)) if ib else 0.0)

        ta = sum(imp_act)
        tb = sum(imp_ant)
        labels2.append('Totales')
        imp_act.append(ta)
        imp_ant.append(tb)
        dif_pct.append(float(round((ta / tb) * 100 - 100, 1)) if tb else 0.0)

    perfil = getattr(request.user, 'perfil', None)
    if perfil:
        categorias_permitidas = set(perfil.categorias_permitidas.values_list('nombre', flat=True))
    else:
        categorias_permitidas = set()

    if request.user.groups.filter(name='administrativos').exists():
        filtered_summary_table = summary_table
    else:
        filtered_summary_table = [
            row for row in summary_table[:-1]
            if row['sede'] in categorias_permitidas
        ]
        if filtered_summary_table:
            filtered_summary_table.append(summary_table[-1])
        else:
            filtered_summary_table = []

    context = {
        'form': form,
        'summary_table': filtered_summary_table,
        'labels1': labels1,
        'ppto_data': ppto_data,
        'venta_data': venta_data,
        'cmp_data': cmp_data,
        'cmp_ant_data': cmp_ant_data,
        'labels2': labels2,
        'imp_act': imp_act,
        'imp_ant': imp_ant,
        'dif_pct': dif_pct,
        'is_administrativo': request.user.groups.filter(name='administrativos').exists(),
    }
    return render(request, 'dashboard_presupuesto.html', context)