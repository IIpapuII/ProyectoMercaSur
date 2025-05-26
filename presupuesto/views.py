import json
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
from .forms import FiltroCumplimientoForm, SedeAñoMesForm, PresupuestoCategoriaFormSet
from .models import Sede, CategoriaVenta, PresupuestoMensualCategoria, PresupuestoDiarioCategoria
from .utils import calcular_presupuesto_con_porcentajes_dinamicos, obtener_clase_semaforo
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from django.db.models import Sum
from appMercaSur.decorators import jwt_login_required

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

@jwt_login_required
def vista_reporte_cumplimiento(request):
    filtro_form = FiltroCumplimientoForm(request.GET or None, user=request.user)
    datos_reporte = []
    resumen_mensual = None
    contexto_filtro = None
    resumen_por_categoria = [] # Inicializamos la nueva lista aquí
    chart_labels, chart_data_ppto, chart_data_venta = [], [], [] # Inicializar para el caso de formulario no válido

    if filtro_form.is_valid():
        sede = filtro_form.cleaned_data['sede']
        categoria_seleccionada = filtro_form.cleaned_data['categoria'] # Para el detalle
        anio = filtro_form.cleaned_data['anio']
        mes = filtro_form.cleaned_data['mes']

        contexto_filtro = {
            'sede_nombre': sede.nombre,
            'categoria_nombre': categoria_seleccionada.nombre, # Para el título del detalle
            'anio': anio,
            'mes': mes
        }

        # --- INICIO: LÓGICA PARA LA TABLA DE RESUMEN GENERAL POR CATEGORÍA ---
        todas_las_categorias = CategoriaVenta.objects.all() # O como obtengas tus categorías activas

        for cat_obj in todas_las_categorias:
            presupuesto_total_cat_qs = PresupuestoDiarioCategoria.objects.filter(
                presupuesto_mensual__sede=sede,
                presupuesto_mensual__categoria=cat_obj,
                presupuesto_mensual__anio=anio,
                presupuesto_mensual__mes=mes
            ).aggregate(total_presupuesto=Sum('presupuesto_calculado'))
            
            presupuesto_total_cat = presupuesto_total_cat_qs['total_presupuesto'] or Decimal('0.00')

            venta_total_cat_qs = VentaDiariaReal.objects.filter(
                sede=sede,
                categoria=cat_obj,
                fecha__year=anio,
                fecha__month=mes
            ).aggregate(total_venta=Sum('venta_real'))
            
            venta_total_cat = venta_total_cat_qs['total_venta'] or Decimal('0.00')

            diferencia_cat = venta_total_cat - presupuesto_total_cat
            cumplimiento_cat_pct = None
            if presupuesto_total_cat > 0:
                cumplimiento_cat_pct = (venta_total_cat / presupuesto_total_cat * Decimal('100')).quantize(Decimal('0.1'), rounding=ROUND_HALF_UP)

            # Solo agregamos si hay presupuesto para esa categoría en el periodo
            if presupuesto_total_cat > 0:
                resumen_por_categoria.append({
                    'nombre_indicador': cat_obj.nombre,
                    'presupuesto_mes': presupuesto_total_cat,
                    'venta_mes': venta_total_cat,
                    'diferencia': diferencia_cat,
                    'cumplimiento_pct': cumplimiento_cat_pct,
                    'semaforo_clase': obtener_clase_semaforo(cumplimiento_cat_pct)
                })
        presupuestos_diarios = PresupuestoDiarioCategoria.objects.filter(
            presupuesto_mensual__sede=sede,
            presupuesto_mensual__categoria=categoria_seleccionada,
            presupuesto_mensual__anio=anio,
            presupuesto_mensual__mes=mes
        ).order_by('fecha')

        if not presupuestos_diarios.exists():
            messages.info(request, f"No se encontraron presupuestos diarios calculados para {categoria_seleccionada.nombre} en {sede.nombre} para el periodo {mes}/{anio}.")
            # No reseteamos las variables del gráfico aquí si ya se calcularon para el resumen
        else:
            ventas_diarias_qs = VentaDiariaReal.objects.filter(
                sede=sede,
                categoria=categoria_seleccionada,
                fecha__year=anio,
                fecha__month=mes
            )
            ventas_map = {v.fecha: v.venta_real for v in ventas_diarias_qs}

            total_ppto_mes_detalle = Decimal('0.00') # Renombrado para evitar confusión con totales de resumen
            total_venta_mes_detalle = Decimal('0.00')
            
            dias_semana_ordenados = ['Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado', 'Domingo']
            resumen_semanal_detalle = { # Renombrado
                dia: {'presupuesto': Decimal('0'), 'venta': Decimal('0')}
                for dia in dias_semana_ordenados
            }

            for ppto_dia in presupuestos_diarios:
                venta_dia_real = ventas_map.get(ppto_dia.fecha, Decimal('0.00'))
                
                nombre_dia = ppto_dia.dia_semana_nombre
                if nombre_dia in resumen_semanal_detalle:
                    resumen_semanal_detalle[nombre_dia]['presupuesto'] += ppto_dia.presupuesto_calculado
                    resumen_semanal_detalle[nombre_dia]['venta'] += venta_dia_real

                diferencia = venta_dia_real - ppto_dia.presupuesto_calculado
                cumplimiento_pct_dia = None # Renombrado
                if ppto_dia.presupuesto_calculado > 0:
                    cumplimiento_pct_dia = (venta_dia_real / ppto_dia.presupuesto_calculado * Decimal('100')).quantize(Decimal('0.1'), rounding=ROUND_HALF_UP)
                
                datos_reporte.append({
                    'fecha': ppto_dia.fecha,
                    'dia_semana': ppto_dia.dia_semana_nombre,
                    'presupuesto_diario': ppto_dia.presupuesto_calculado,
                    'venta_diaria': venta_dia_real,
                    'diferencia': diferencia,
                    'cumplimiento_pct': cumplimiento_pct_dia,
                    'semaforo_clase': obtener_clase_semaforo(cumplimiento_pct_dia) # Usar el mismo semáforo
                })

                total_ppto_mes_detalle += ppto_dia.presupuesto_calculado
                total_venta_mes_detalle += venta_dia_real
            
            # Datos para el gráfico del detalle
            chart_labels = dias_semana_ordenados
            chart_data_ppto = [float(resumen_semanal_detalle[dia]['presupuesto']) for dia in dias_semana_ordenados]
            chart_data_venta = [float(resumen_semanal_detalle[dia]['venta']) for dia in dias_semana_ordenados]

            cumplimiento_total_mes_detalle = None # Renombrado
            if total_ppto_mes_detalle > 0:
                cumplimiento_total_mes_detalle = (total_venta_mes_detalle / total_ppto_mes_detalle * Decimal('100')).quantize(Decimal('0.1'), rounding=ROUND_HALF_UP)

            resumen_mensual = { # Este es el resumen del pie de la tabla de detalle
                'total_presupuesto': total_ppto_mes_detalle,
                'total_venta': total_venta_mes_detalle,
                'total_diferencia': total_venta_mes_detalle - total_ppto_mes_detalle,
                'cumplimiento_pct': cumplimiento_total_mes_detalle,
                'semaforo_clase': obtener_clase_semaforo(cumplimiento_total_mes_detalle)
            }
            if not datos_reporte and presupuestos_diarios.exists(): # Ajuste en la condición del mensaje
                 messages.info(request, f"Se encontraron presupuestos para {categoria_seleccionada.nombre} en {sede.nombre} para {mes}/{anio}, pero no se generaron datos de ventas para el detalle diario.")
    # else: # Si el formulario no es válido, las variables del gráfico ya están inicializadas como listas vacías

    context = {
        'filtro_form': filtro_form,
        'resumen_por_categoria': resumen_por_categoria, # Añadido al contexto
        'datos_reporte': datos_reporte,
        'resumen_mensual': resumen_mensual,
        'contexto_filtro': contexto_filtro,
        'chart_labels': mark_safe(json.dumps(chart_labels)),
        'chart_data_ppto': mark_safe(json.dumps(chart_data_ppto)),
        'chart_data_venta': mark_safe(json.dumps(chart_data_venta)),
    }
    return render(request, 'reporte_cumplimiento.html', context)