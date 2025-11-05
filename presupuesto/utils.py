# tu_app/utils.py
import calendar
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation

from appMercaSur.conect import conectar_sql_server
from .models import CategoriaVenta, PorcentajeDiarioConfig, PresupuestoDiarioCategoria, PresupuestoMensualCategoria, Sede # Importar modelos necesarios
import pandas as pd
from prophet import Prophet
from .models import VentaDiariaReal
from calendar import monthrange
from django.db import transaction


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
    print('Ingreso ha este proceso')
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



def cargar_ventas_reales_carne(fecha_inicio, fecha_fin):
    """
    Carga o actualiza las ventas reales por sede y categoría
    entre fecha_inicio y fecha_fin.
    :param fecha_inicio: fecha inicial (string 'YYYY-MM-DD' o date)
    :param fecha_fin: fecha final (string 'YYYY-MM-DD' o date)
    """
    sql = '''
    WITH VentasDetalle AS (
        SELECT
            AL.CODALMACEN,
            AR.CODARTICULO,
            AL.UNID1,
            ROUND(AL.PRECIO * (1 - AL.DTO / 100.0) * AL.UNID1, 2) AS ImporteConDescuento,
            AR.TIPO,
            AR.TIPOARTICULO,
            AR.DPTO,
            AR.MARCA,
            AC.FECHA AS fechaVenta,
            (CASE WHEN (AL.DTO = 0 AND AL.PRECIO = 0 AND AL.PRECIODEFECTO > 0 AND AL.UNIDADESTOTAL > 0)
                THEN (AL.UNIDADESTOTAL * AL.PRECIODEFECTO)
                ELSE 0
             END) AS Post
        FROM ALBVENTALIN AL
        INNER JOIN ALBVENTACAB AC
            ON AL.NUMSERIE = AC.NUMSERIE
            AND AL.NUMALBARAN = AC.NUMALBARAN
            AND AL.N = AC.N
        INNER JOIN ARTICULOS AR
            ON AL.CODARTICULO = AR.CODARTICULO
        WHERE TRY_CONVERT(DATE, AC.FECHA, 105) BETWEEN ? AND ?
          AND AC.TIPODOC IN ('13','82','83')
          AND AR.DPTO <> 103
          AND AR.DPTO = 50
    ),
    VentasAgrupadas AS (
        SELECT
            CODALMACEN,
            SUM(CASE WHEN DPTO = 50 THEN ImporteConDescuento + Post ELSE 0 END) AS CARNE,
            fechaVenta
        FROM VentasDetalle
        GROUP BY CODALMACEN, fechaVenta
    ),
    AlmacenesInfo AS (
        SELECT '1' AS Cod, 'CALDAS' AS Nombre UNION ALL
        SELECT '2', 'CENTRO' UNION ALL
        SELECT '3', 'CABECERA'
    )
    SELECT
        AI.Nombre AS sede_nombre,
        'CONCESION CARNE' AS categoria_nombre,
        VA.fechaVenta AS fecha,
        ISNULL(VA.CARNE, 0) AS venta_real,
        0 AS margen_sin_post_pct,
        100 AS margen_con_post_pct
    FROM AlmacenesInfo AI
    LEFT JOIN VentasAgrupadas VA
        ON AI.Cod = VA.CODALMACEN
    ORDER BY
        CASE AI.Cod
            WHEN '1' THEN 1
            WHEN '2' THEN 2
            WHEN '3' THEN 3
            ELSE 4
        END;
    '''
    conexion = conectar_sql_server()
    cursor =conexion.cursor()
    cursor.execute(sql, [fecha_inicio, fecha_fin])
    filas = cursor.fetchall()

    # Asumiendo que existe una sola categoría con nombre 'CONCESION CARNE'
    categoria_obj, _ = CategoriaVenta.objects.get_or_create(
        nombre='CONCESION CARNE'
    )

    with transaction.atomic():
        for sede_nombre, _, fecha_raw, venta_real, margen_sin, margen_con in filas:
            sede_obj = Sede.objects.get(nombre=sede_nombre)
            fecha = fecha_raw or fecha_inicio
            # Intentamos obtener el registro existente
            obj, created = VentaDiariaReal.objects.update_or_create(
                sede=sede_obj,
                categoria=categoria_obj,
                fecha=fecha,
                defaults={
                    'venta_real': Decimal(venta_real),
                    'margen_sin_post_pct': Decimal(margen_sin),
                    'margen_con_post_pct': Decimal(margen_con),
                }
            )
            if not created:
                # Si ya existía, simplemente actualizamos los campos y guardamos
                obj.venta_real = Decimal(venta_real)
                obj.margen_sin_post_pct = Decimal(margen_sin)
                obj.margen_con_post_pct = Decimal(margen_con)
                obj.save()
    print(f"Cargadas {len(filas)} filas de ventas reales entre {fecha_inicio} y {fecha_fin}.")

def cargasr_ventas_reales_ecenarios(fecha_inicio, fecha_fin):
    """
    Carga o actualiza las ventas reales por sede y categoría
    entre fecha_inicio y fecha_fin para TODAS las categorías principales.
    """
    sql = '''
    WITH VentasDetalle AS (
    SELECT
        AL.CODALMACEN,
        CAST(AC.FECHA AS DATE) AS fechaVenta,
        AR.TIPO,
        AR.DPTO,
        AR.MARCA,
        AR.LINEA,
        -- clamp DTO a [0..100] y castea a DECIMAL
        CAST(
            AL.PRECIO * (1 - (
                CASE 
                    WHEN COALESCE(AL.DTO,0) < 0 THEN 0
                    WHEN COALESCE(AL.DTO,0) > 100 THEN 100
                    ELSE COALESCE(AL.DTO,0)
                END
            ) / 100.0) * AL.UNID1
        AS DECIMAL(18,2)) AS ImporteNeto,
        CAST(AL.COSTE * AL.UNID1 AS DECIMAL(18,2)) AS CosteLinea,
        CAST(
            (AL.PRECIOIVA * (
                CASE 
                    WHEN COALESCE(AL.DTO,0) < 0 THEN 0
                    WHEN COALESCE(AL.DTO,0) > 100 THEN 100
                    ELSE COALESCE(AL.DTO,0)
                END
            ) / 100.0) * AL.UNID1
            + CASE
                WHEN AL.PRECIO = 0 AND AL.PRECIODEFECTO > 0
                THEN AL.PRECIODEFECTO * AL.UNID1
                ELSE 0
              END
        AS DECIMAL(18,2)) AS POS
    FROM ALBVENTALIN AL
    JOIN ALBVENTACAB AC
      ON AC.NUMSERIE = AL.NUMSERIE AND AC.NUMALBARAN = AL.NUMALBARAN
    JOIN ARTICULOS AR
      ON AR.CODARTICULO = AL.CODARTICULO
    WHERE
        CAST(AC.FECHA AS DATE) BETWEEN ? AND ?
        AND AC.TIPODOC IN (13, 82, 83)
        AND AR.DPTO <> 103
),
Categorias AS (
    -- ESCENARIOS
    SELECT
        VD.CODALMACEN,
        VD.fechaVenta,
        'ESCENARIOS' AS CATEGORIA,
        CAST(COALESCE(SUM(ImporteNeto), 0) AS DECIMAL(18,2)) AS VENTA_NETA,
        CAST(COALESCE(SUM(POS), 0)        AS DECIMAL(18,2)) AS VALOR_POS,
        CAST(COALESCE(SUM(CosteLinea), 0) AS DECIMAL(18,2)) AS COSTE
    FROM VentasDetalle VD
    WHERE VD.TIPO <> 2
    GROUP BY VD.CODALMACEN, VD.fechaVenta

    UNION ALL
    -- FRUVER
    SELECT
        VD.CODALMACEN,
        VD.fechaVenta,
        'FRUVER',
        CAST(COALESCE(SUM(ImporteNeto), 0) AS DECIMAL(18,2)),
        CAST(COALESCE(SUM(POS), 0)        AS DECIMAL(18,2)),
        CAST(COALESCE(SUM(CosteLinea), 0) AS DECIMAL(18,2))
    FROM VentasDetalle VD
    WHERE VD.TIPO <> 2 AND VD.DPTO = 5
    GROUP BY VD.CODALMACEN, VD.fechaVenta

    UNION ALL
    -- PANADERIA
    SELECT
        VD.CODALMACEN,
        VD.fechaVenta,
        'PANADERIA',
        CAST(COALESCE(SUM(ImporteNeto), 0) AS DECIMAL(18,2)),
        CAST(COALESCE(SUM(POS), 0)        AS DECIMAL(18,2)),
        CAST(COALESCE(SUM(CosteLinea), 0) AS DECIMAL(18,2))
    FROM VentasDetalle VD
    WHERE VD.MARCA = 4
    GROUP BY VD.CODALMACEN, VD.fechaVenta

    UNION ALL
    -- MARCA MERCASUR
    SELECT
        VD.CODALMACEN,
        VD.fechaVenta,
        'MARCA MERCASUR',
        CAST(COALESCE(SUM(ImporteNeto), 0) AS DECIMAL(18,2)),
        CAST(COALESCE(SUM(POS), 0)        AS DECIMAL(18,2)),
        CAST(COALESCE(SUM(CosteLinea), 0) AS DECIMAL(18,2))
    FROM VentasDetalle VD
    WHERE VD.LINEA = '1' AND VD.TIPO <> 9
    GROUP BY VD.CODALMACEN, VD.fechaVenta
),
AlmacenesInfo AS (
    SELECT '1' AS Cod, 'CALDAS' AS Nombre
    UNION ALL SELECT '2', 'CENTRO'
    UNION ALL SELECT '3', 'CABECERA'
    UNION ALL SELECT '50', 'SOTOMAYOR'
)
SELECT
    AI.Nombre AS ALMACEN,
    C.CATEGORIA,
    CAST(C.VENTA_NETA + C.VALOR_POS AS DECIMAL(18,2)) AS VALOR,
    CASE WHEN C.VENTA_NETA = 0 THEN 0
         ELSE (100.0 * (C.VENTA_NETA - C.COSTE) / NULLIF(C.VENTA_NETA, 0)) END AS PCT_MARGEN_SIN_POS,
    CASE WHEN (C.VENTA_NETA + C.VALOR_POS) = 0 THEN 0
         ELSE (100.0 * ((C.VENTA_NETA + C.VALOR_POS) - C.COSTE) / NULLIF((C.VENTA_NETA + C.VALOR_POS), 0)) END AS PCT_MARGEN_CON_POS,
    C.fechaVenta
FROM AlmacenesInfo AI
LEFT JOIN Categorias C ON AI.Cod = C.CODALMACEN
WHERE C.fechaVenta IS NOT NULL
ORDER BY AI.Nombre, C.fechaVenta, C.CATEGORIA
    '''
    conexion = conectar_sql_server()
    cursor = conexion.cursor()
    cursor.execute(sql, [fecha_inicio, fecha_fin])
    filas = cursor.fetchall()

    with transaction.atomic():
        for sede_nombre, categoria_nombre, venta_real, margen_sin, margen_con, fecha_raw,  in filas:
            # Obtener o crear la sede
            sede_obj = Sede.objects.get(nombre=sede_nombre)
            # Obtener o crear la categoría (¡aquí es donde cambia!)
            categoria_obj, _ = CategoriaVenta.objects.get_or_create(
                nombre=categoria_nombre
            )
            fecha = fecha_raw or fecha_inicio
            # Actualiza o crea
            obj, created = VentaDiariaReal.objects.update_or_create(
                sede=sede_obj,
                categoria=categoria_obj,
                fecha=fecha,
                defaults={
                    'venta_real': Decimal(venta_real),
                    'margen_sin_post_pct': Decimal(margen_sin),
                    'margen_con_post_pct': Decimal(margen_con),
                }
            )
            if not created:
                obj.venta_real = Decimal(venta_real)
                obj.margen_sin_post_pct = Decimal(margen_sin)
                obj.margen_con_post_pct = Decimal(margen_con)
                obj.save()
    print(f"Cargadas {len(filas)} filas de ventas reales de todas las categorías entre {fecha_inicio} y {fecha_fin}.")

def calcular_presupuesto_diario_forecast(presupuesto_mensual_obj):
    """
    Calcula y actualiza el presupuesto diario para una categoría/sede usando Prophet,
    incorporando el efecto de eventos históricos si existen.
    """

    anio_obj = presupuesto_mensual_obj.anio
    mes_obj = presupuesto_mensual_obj.mes
    sede = presupuesto_mensual_obj.sede
    categoria = presupuesto_mensual_obj.categoria
    valor_mes = float(presupuesto_mensual_obj.presupuesto_total_categoria) 

    fecha_inicio = date(anio_obj, 1, 1)
    if mes_obj == 1:
        raise Exception("No hay histórico suficiente para calcular enero.")
    else:
        fecha_fin = date(anio_obj, mes_obj - 1, monthrange(anio_obj, mes_obj - 1)[1])

    # Obtener ventas históricas y eventos asociados
    ventas = list(VentaDiariaReal.objects.filter(
        sede=sede,
        categoria=categoria,
        fecha__gte=fecha_inicio,
        fecha__lte=fecha_fin
    ).values('fecha', 'venta_real', 'Eventos'))

    if not ventas or len(ventas) < 30:
        raise Exception("No hay suficiente historial para hacer forecast diario.")

    df = pd.DataFrame(ventas)
    df = df.rename(columns={'fecha': 'ds', 'venta_real': 'y'})
    df['ds'] = pd.to_datetime(df['ds'])

    # Crear columna binaria 'evento' para Prophet
    df['evento'] = df['Eventos'].notnull().astype(int)
    df = df.drop(columns=['Eventos'])

    # Configurar modelo Prophet con regresor de evento
    modelo = Prophet(yearly_seasonality=False, daily_seasonality=False, weekly_seasonality=True)
    modelo.add_regressor('evento')
    modelo.fit(df)

    # Generar fechas del mes objetivo
    primer_dia = date(anio_obj, mes_obj, 1)
    ultimo_dia = date(anio_obj, mes_obj, monthrange(anio_obj, mes_obj)[1])
    fechas_mes = pd.date_range(primer_dia, ultimo_dia)

    # Preparar input de predicción con columna evento=0 (si no se conocen eventos futuros)
    futuro = pd.DataFrame({'ds': fechas_mes})
    futuro['evento'] = 0  # Asume que no hay eventos conocidos en el futuro

    forecast = modelo.predict(futuro)
    forecast['yhat'] = forecast['yhat'].clip(lower=0)

    total_mes = forecast['yhat'].sum()
    if total_mes == 0:
        raise Exception("La predicción del mes objetivo es cero. Revisa los datos históricos.")
    forecast['pct_dia'] = forecast['yhat'] / total_mes

    # Mapeo de eventos históricos por fecha
    eventos_por_fecha = {
        v['fecha']: v.get('Eventos') for v in ventas if v.get('Eventos')
    }

    # Nombres de días en español
    nombres_es = {
        'Monday': 'Lunes', 'Tuesday': 'Martes', 'Wednesday': 'Miércoles',
        'Thursday': 'Jueves', 'Friday': 'Viernes', 'Saturday': 'Sábado', 'Sunday': 'Domingo'
    }

    # Guardar presupuestos diarios
    for _, row in forecast.iterrows():
        fecha_dia = row['ds'].date()
        pct = Decimal(row['pct_dia'] * 100).quantize(Decimal('0.01'))
        valor = Decimal(row['pct_dia'] * valor_mes).quantize(Decimal('0.01'))
        dia_semana = nombres_es[row['ds'].day_name()]
        evento_asociado = eventos_por_fecha.get(fecha_dia)

        PresupuestoDiarioCategoria.objects.update_or_create(
            presupuesto_mensual=presupuesto_mensual_obj,
            fecha=fecha_dia,
            defaults={
                'dia_semana_nombre': dia_semana,
                'porcentaje_dia_especifico': pct,
                'presupuesto_calculado': valor
            }
        )

    return f"Presupuesto diario calculado para {sede} / {categoria} en {anio_obj}-{mes_obj}"

from decimal import Decimal, ROUND_HALF_UP

def ajustar_presupuesto_diario(presupuesto_mensual_obj, dia_modificado, nuevo_porcentaje):
    """
    Ajusta los porcentajes de los días del mes para que sumen 100%,
    recalcula los valores diarios y los guarda.
    El ajuste se hace distribuyendo la diferencia proporcionalmente entre los demás días.
    """
    print(f"Ajustando presupuesto diario para {presupuesto_mensual_obj} en el día {dia_modificado} con nuevo porcentaje {nuevo_porcentaje}")
    presupuesto_mensual_obj.refresh_from_db()

    dias = list(presupuesto_mensual_obj.dias_calculados.order_by('fecha'))
    total_dias = len(dias)
    if total_dias == 0:
        return False, "No hay días para ajustar."

    # Identificar el día modificado y los otros días
    dia_mod = next((d for d in dias if d.fecha == dia_modificado), None)
    otros_dias = [d for d in dias if d.fecha != dia_modificado]
    if not dia_mod:
        return False, "No se encontró el día modificado."

    # Calcular el porcentaje restante a repartir
    nuevo_porcentaje = Decimal(nuevo_porcentaje).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    restante = Decimal('100.00') - nuevo_porcentaje

    if restante < 0:
        return False, "El porcentaje asignado excede el 100%."

    suma_otros_actual = sum(d.porcentaje_dia_especifico for d in otros_dias)
    if suma_otros_actual == 0:
        # Si todos los demás días estaban en 0, repartir equitativamente
        for d in otros_dias:
            d.porcentaje_dia_especifico = (restante / len(otros_dias)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    else:
        # Ajustar proporcionalmente los porcentajes de los otros días
        for d in otros_dias:
            proporcion = d.porcentaje_dia_especifico / suma_otros_actual if suma_otros_actual else Decimal('0')
            d.porcentaje_dia_especifico = (restante * proporcion).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

    # Asignar el nuevo porcentaje al día modificado
    dia_mod.porcentaje_dia_especifico = nuevo_porcentaje

    # Ajuste final para asegurar que la suma sea exactamente 100.00 (por redondeos)
    suma_final = sum(d.porcentaje_dia_especifico for d in dias)
    diferencia = Decimal('100.00') - suma_final
    if abs(diferencia) >= Decimal('0.01'):
        # Ajustar el primer día distinto al modificado (o el modificado si es el único)
        for d in dias:
            if d != dia_mod or len(dias) == 1:
                d.porcentaje_dia_especifico += diferencia
                break

    # Recalcular los valores diarios para que sumen el presupuesto mensual
    presupuesto_mensual = presupuesto_mensual_obj.presupuesto_total_categoria
    for d in dias:
        d.presupuesto_calculado = (presupuesto_mensual * d.porcentaje_dia_especifico / Decimal('100.00')).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        d.save()

    return True, "Presupuesto diario ajustado correctamente."

def formato_dinero_colombiano(valor):
    """
    Formatea un número como dinero colombiano: $ 1.234.567,89
    """
    try:
        valor = float(valor)
        return "${:,.2f}".format(valor).replace(',', 'X').replace('.', ',').replace('X', '.')
    except (TypeError, ValueError):
        return "-"