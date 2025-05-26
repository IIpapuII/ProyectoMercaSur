# tu_app/utils.py
import calendar
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation
from .models import CategoriaVenta, PorcentajeDiarioConfig, PresupuestoDiarioCategoria, PresupuestoMensualCategoria # Importar modelos necesarios

def calcular_presupuesto_con_porcentajes_dinamicos(sede_id, anio, mes, presupuestos_input_por_categoria):
    """
    Calcula presupuestos diarios usando el Método A:
    ValorDiario = (PresupuestoMensual * PctDia / 100) / NumOcurrenciasDia.

    Args:
        anio (int): El año.
        mes (int): El mes (1-12).
        presupuestos_input_por_categoria (dict):
            {'NombreCategoria1': Decimal('PresupuestoMensual1'), ...}

    Returns:
        tuple: (resultados_por_dia, totales_finales_categoria, gran_total_componentes)
               - resultados_por_dia (list): Lista de dicts diarios con desglose por categoría.
               - totales_finales_categoria (dict): Suma final ajustada por categoría.
               - gran_total_componentes (Decimal): Suma final de los componentes (excl. Total Sede).
               Retorna (None, None, None) si hay error fundamental.
    """
    print(f"Iniciando cálculo (Método A) para Sede ID: {sede_id}, Periodo: {mes}/{anio}")
    if not (1 <= mes <= 12):
        print("Error: Mes inválido.")
        return None, None, None

    try:
        primer_dia_mes = date(anio, mes, 1)
        num_dias_en_mes = calendar.monthrange(anio, mes)[1]
    except ValueError:
        print(f"Error: Año ({anio}) o mes ({mes}) inválido.")
        return None, None, None

    # 1. Obtener configuraciones de porcentaje y validar (igual que antes)
    mapa_porcentajes_categoria = {} # {'NombreCategoria': {0: PctLu, 1: PctMa, ...}}
    categorias_validas = []
    for nombre_cat, presupuesto_val in presupuestos_input_por_categoria.items():
        try:
            presupuesto_decimal = Decimal(presupuesto_val) if presupuesto_val is not None else Decimal('0.00')
            if presupuesto_decimal < 0: presupuesto_decimal = Decimal('0.00')
            presupuestos_input_por_categoria[nombre_cat] = presupuesto_decimal # Asegurar Decimal

            categoria_obj = CategoriaVenta.objects.get(nombre=nombre_cat)
            configs = PorcentajeDiarioConfig.objects.filter(categoria=categoria_obj, sede =sede_id)
            if configs.count() != 7:
                print(f"Error Crítico: '{nombre_cat}' no tiene 7 porcentajes diarios configurados.")
                continue # Saltar categoría

            mapa_porcentajes_categoria[nombre_cat] = {c.dia_semana: c.porcentaje for c in configs}
            suma_pct = sum(mapa_porcentajes_categoria[nombre_cat].values())
            if suma_pct != Decimal('100.00'):
                print(f"Advertencia: Los porcentajes para '{nombre_cat}' no suman 100.00 (Suma: {suma_pct}). Los resultados podrían no ser los esperados conceptualmente.")

            categorias_validas.append(nombre_cat)

        except CategoriaVenta.DoesNotExist:
            print(f"Error: Categoría '{nombre_cat}' no encontrada.")
        except (InvalidOperation, TypeError):
            print(f"Error: Valor de presupuesto inválido para '{nombre_cat}'. Se usará 0.")
            presupuestos_input_por_categoria[nombre_cat] = Decimal('0.00')

    if not categorias_validas:
         print("Error: No hay categorías válidas con porcentajes configurados para procesar.")
         return None, None, None

    # 2. Calcular número de ocurrencias de cada día de la semana en el mes (igual que antes)
    dias_semana_ocurrencias = {i: 0 for i in range(7)}
    fechas_del_mes_info = []
    nombres_dias_map = {0: 'Lunes', 1: 'Martes', 2: 'Miércoles', 3: 'Jueves', 4: 'Viernes', 5: 'Sábado', 6: 'Domingo'}
    for i in range(num_dias_en_mes):
        fecha_actual = primer_dia_mes + timedelta(days=i)
        dia_idx = fecha_actual.weekday()
        dias_semana_ocurrencias[dia_idx] += 1
        fechas_del_mes_info.append({
            'fecha': fecha_actual,
            'dia_semana_idx': dia_idx,
            'dia_semana_nombre': nombres_dias_map[dia_idx]
        })

    # 3. Calcular la TARIFA DIARIA BRUTA para cada tipo de día (Lun, Mar...) para cada categoría
    mapa_tarifas_diarias_brutas = {} # {'NombreCat': {0: TarifaLun, 1: TarifaMar, ...}}
    for nombre_cat in categorias_validas:
        mapa_tarifas_diarias_brutas[nombre_cat] = {}
        presupuesto_mensual_cat = presupuestos_input_por_categoria[nombre_cat]
        porcentajes_cat = mapa_porcentajes_categoria[nombre_cat]

        for dia_idx in range(7): # 0 a 6
            porcentaje_dia = porcentajes_cat.get(dia_idx, Decimal('0'))
            num_ocurrencias = dias_semana_ocurrencias[dia_idx]

            # Calcular porción del presupuesto para este tipo de día
            presupuesto_total_para_tipo_dia = presupuesto_mensual_cat * (porcentaje_dia / Decimal('100'))

            # Calcular tarifa diaria bruta
            tarifa_diaria_bruta = Decimal('0.00')
            if num_ocurrencias > 0:
                # Dividir la porción entre el número de veces que ocurre el día
                tarifa_diaria_bruta = (presupuesto_total_para_tipo_dia / Decimal(num_ocurrencias)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
            # Si num_ocurrencias es 0, la tarifa se queda en 0 (ese día no existe en el mes)

            mapa_tarifas_diarias_brutas[nombre_cat][dia_idx] = tarifa_diaria_bruta

    # 4. Construir resultados diarios brutos y calcular sumas brutas
    resultados_brutos_por_dia = []
    sumas_brutas_por_categoria = {nombre_cat: Decimal('0') for nombre_cat in categorias_validas}

    for info_dia in fechas_del_mes_info:
        dia_idx_actual = info_dia['dia_semana_idx']
        dia_actual_data_bruta = {
            'fecha': info_dia['fecha'],
            'dia_semana_nombre': info_dia['dia_semana_nombre'],
            'budgets_by_category': {},
            'total_dia_componentes': Decimal('0')
        }

        for nombre_cat_loop in categorias_validas:
            # Obtener la tarifa diaria precalculada para este día/categoría
            tarifa_calculada = mapa_tarifas_diarias_brutas[nombre_cat_loop].get(dia_idx_actual, Decimal('0.00'))
            # Obtener el porcentaje usado (para mostrarlo)
            porcentaje_usado = mapa_porcentajes_categoria[nombre_cat_loop].get(dia_idx_actual, Decimal('0'))

            dia_actual_data_bruta['budgets_by_category'][nombre_cat_loop] = {
                'valor': tarifa_calculada,
                'porcentaje_usado': porcentaje_usado
            }
            sumas_brutas_por_categoria[nombre_cat_loop] += tarifa_calculada

            if nombre_cat_loop != "Total Sede":
                 dia_actual_data_bruta['total_dia_componentes'] += tarifa_calculada

        resultados_brutos_por_dia.append(dia_actual_data_bruta)

    # 5. Pase de Ajuste para cuadrar totales por categoría (AÚN RECOMENDADO por posibles redondeos)
    resultados_ajustados_por_dia = []
    totales_finales_por_categoria = {nombre_cat: Decimal('0') for nombre_cat in categorias_validas}
    gran_total_componentes_final = Decimal('0')

    for i, dia_data_bruta in enumerate(resultados_brutos_por_dia):
        # Copiar datos básicos del día
        data_dia_ajustado = {
            'fecha': dia_data_bruta['fecha'],
            'dia_semana_nombre': dia_data_bruta['dia_semana_nombre'],
            'budgets_by_category': {},
            'total_dia_componentes': Decimal('0')
        }
        for nombre_cat, data_cat_bruta in dia_data_bruta['budgets_by_category'].items():
            presupuesto_bruto_cat_dia = data_cat_bruta['valor']
            presupuesto_final_cat_dia = presupuesto_bruto_cat_dia

            # Ajustar en el último día del mes para esta categoría
            if i == num_dias_en_mes - 1:
                presupuesto_mensual_input_cat = presupuestos_input_por_categoria[nombre_cat]
                suma_bruta_actual = sumas_brutas_por_categoria[nombre_cat]
                diferencia = presupuesto_mensual_input_cat - suma_bruta_actual
                # Solo aplicar si la diferencia es significativa para evitar cambios por precisión de Decimal
                # if abs(diferencia) > Decimal('0.005') * len(resultados_brutos_por_dia): # Heurística opcional
                presupuesto_final_cat_dia += diferencia
                if diferencia != Decimal('0.00'):
                     print(f"Ajuste último día para '{nombre_cat}': {diferencia:.2f}")


            # Redondeo final del valor diario ajustado
            presupuesto_final_cat_dia = presupuesto_final_cat_dia.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

            data_dia_ajustado['budgets_by_category'][nombre_cat] = {
                'valor': presupuesto_final_cat_dia,
                'porcentaje_usado': data_cat_bruta['porcentaje_usado']
            }
            # Acumular suma final por categoría
            totales_finales_por_categoria[nombre_cat] += presupuesto_final_cat_dia

            # Acumular suma de componentes del día (excluyendo "Total Sede")
            if nombre_cat != "Total Sede":
                 data_dia_ajustado['total_dia_componentes'] += presupuesto_final_cat_dia

        # Redondear suma del día de componentes
        data_dia_ajustado['total_dia_componentes'] = data_dia_ajustado['total_dia_componentes'].quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        resultados_ajustados_por_dia.append(data_dia_ajustado)
        # Acumular gran total de componentes
        gran_total_componentes_final += data_dia_ajustado['total_dia_componentes']

    # Redondeo final de los totales acumulados por categoría
    for cat_n in totales_finales_por_categoria:
        totales_finales_por_categoria[cat_n] = totales_finales_por_categoria[cat_n].quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

    print("Cálculo finalizado (Método A).")
    return (
        resultados_ajustados_por_dia,
        totales_finales_por_categoria,
        gran_total_componentes_final.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    )

def obtener_clase_semaforo(cumplimiento_pct):
    """
    Función mejorada para devolver clases estilo mapa de calor.
    """
    if cumplimiento_pct is None:
        return 'heatmap-na'  
    if cumplimiento_pct < 90:
        return 'heatmap-1'  
    if cumplimiento_pct < 95:
        return 'heatmap-2'  
    if cumplimiento_pct < 97:
        return 'heatmap-3'  
    if cumplimiento_pct <= 101:
        return 'heatmap-4'  
    
    return 'heatmap-5' 

def recalcular_presupuestos_diarios_para_periodo(sede_id, anio, mes):
    """
    Función central que recalcula y guarda los presupuestos diarios para una sede/periodo.
    Esta función será llamada desde la señal y desde la vista.
    """
    print(f"--- Iniciando recálculo para Sede ID: {sede_id}, Periodo: {mes}/{anio} ---")
    
    # 1. Recolectar todos los presupuestos mensuales para el periodo/sede dados.
    presupuestos_mensuales = PresupuestoMensualCategoria.objects.filter(
        sede_id=sede_id, anio=anio, mes=mes
    )
    
    if not presupuestos_mensuales.exists():
        print("No se encontraron presupuestos mensuales para este periodo. No se hace nada.")
        return False, "No se encontraron presupuestos mensuales para recalcular."

    # Construir el diccionario que la función de cálculo espera
    presupuestos_input = {
        pm.categoria.nombre: pm.presupuesto_total_categoria
        for pm in presupuestos_mensuales
    }

    # 2. Llamar a la función de cálculo original.
    resultados_diarios, _, _ = calcular_presupuesto_con_porcentajes_dinamicos(
        sede_id, anio, mes, presupuestos_input
    )

    if resultados_diarios is None:
        print("El cálculo falló. Revisa la configuración de porcentajes.")
        return False, "Falló el cálculo. Revisa la configuración de porcentajes."

    # 3. Guardar los nuevos resultados en la base de datos (lógica extraída de tu vista).
    # Primero, borrar los registros diarios antiguos para este periodo y sede.
    PresupuestoDiarioCategoria.objects.filter(
        presupuesto_mensual__in=presupuestos_mensuales
    ).delete()

    # Luego, crear los nuevos registros diarios en bloque.
    nuevos_diarios = []
    for dia_data in resultados_diarios:
        for cat_nombre, datos_cat_dia in dia_data['budgets_by_category'].items():
            try:
                # Encontrar el objeto PresupuestoMensualCategoria correspondiente
                presup_mensual_obj = next(
                    pm for pm in presupuestos_mensuales if pm.categoria.nombre == cat_nombre
                )
                
                nuevos_diarios.append(PresupuestoDiarioCategoria(
                    presupuesto_mensual=presup_mensual_obj,
                    fecha=dia_data['fecha'],
                    dia_semana_nombre=dia_data['dia_semana_nombre'],
                    porcentaje_dia_especifico=datos_cat_dia['porcentaje_usado'],
                    presupuesto_calculado=datos_cat_dia['valor']
                ))
            except StopIteration:
                print(f"Advertencia: No se encontró PresupuestoMensual para {cat_nombre} al guardar diarios.")

    if nuevos_diarios:
        PresupuestoDiarioCategoria.objects.bulk_create(nuevos_diarios)
        print(f"Cálculo exitoso: {len(nuevos_diarios)} registros diarios guardados/actualizados.")
        return True, "Cálculo realizado y guardado con éxito."
    
    return False, "No se generaron nuevos registros diarios."