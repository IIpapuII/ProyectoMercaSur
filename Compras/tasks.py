from django.db import models
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from appMercaSur.conect import conectar_sql_server, ejecutar_consulta
from .utils import get_campo_clasificacion_por_almacen
from Compras.models import ProcesoClasificacion, ArticuloClasificacionTemporal, ArticuloClasificacionFinal
from celery import shared_task
from .utils import notificar_proceso_finalizado, notificar_proceso_con_excel, procesar_clasificacion
from datetime import date, timedelta

@shared_task()
def cargar_proceso_clasificacion_task( user_id: int | None = None):
    """
    Task de Celery para extraer datos de ICG y poblar los modelos ProcesoClasificacion
    y ArticuloClasificacionTemporal.

    :param user_id: ID del usuario que dispara el proceso (opcional).
    :return: Mensaje de resultado.
    """
    # Obtener usuario si existe
    usuario = None
    if user_id:
        User = get_user_model()
        try:
            usuario = User.objects.get(pk=user_id)
        except User.DoesNotExist:
            usuario = None

    # Crear registro de proceso
    proceso = ProcesoClasificacion.objects.create(
        usuario=usuario,
        descripcion='Carga por Celery'
    )

    # Conectar a ICG
    conexion = conectar_sql_server()
    if not conexion:
        proceso.estado = 'procesado'
        proceso.save(update_fields=['estado'])
        return f"Fallo de conexión a ICG en Proceso #{proceso.pk}"

    # Calcular fechas: últimos 4 meses desde hoy
    hoy = date.today()
    primer_dia_mes_actual = hoy.replace(day=1)
    # Restar 4 meses
    mes_inicio = primer_dia_mes_actual.month - 4
    anio_inicio = primer_dia_mes_actual.year
    while mes_inicio <= 0:
        mes_inicio += 12
        anio_inicio -= 1
    fecha_inicio = date(anio_inicio, mes_inicio, 1)
    # Último día del mes anterior al actual
    fecha_fin = primer_dia_mes_actual - timedelta(days=1)

    # Consulta SQL para extraer datos
    consulta = f"""
;WITH VentasFiltradas AS (
    SELECT
        AL.CODALMACEN,
        AL.CODARTICULO,
        AL.UNID1,
        AL.PRECIO,
        AL.DTO,
        AL.PRECIODEFECTO,
        AL.UNIDADESTOTAL
    FROM ALBVENTALIN AL
    INNER JOIN ALBVENTACAB AC
        ON AL.NUMSERIE = AC.NUMSERIE
       AND AL.NUMALBARAN = AC.NUMALBARAN
       AND AL.N = AC.N
    WHERE TRY_CONVERT(date, AC.FECHA, 105)  BETWEEN '{fecha_inicio}' AND '{fecha_fin}'
      AND AC.TIPODOC IN ('13','82','83')
      AND AL.CODALMACEN IN ('1','2','3','50')
),
VentasDetalle AS (   -- 1 fila por (almacén, artículo)
    SELECT
        CODALMACEN,
        CODARTICULO,
        SUM(UNID1) AS Unidad,
        SUM(ROUND(PRECIO * (1 - DTO / 100.0) * UNID1, 2)) +
        SUM(CASE 
                WHEN (DTO = 0 AND PRECIO = 0 AND PRECIODEFECTO > 0 AND UNIDADESTOTAL > 0)
                     THEN (UNIDADESTOTAL * PRECIODEFECTO)
                ELSE 0
            END) AS Importe
    FROM VentasFiltradas
    GROUP BY CODALMACEN, CODARTICULO
),
StockAgg AS (        -- 1 fila por (almacén, artículo)
    SELECT
        S.CODALMACEN,
        S.CODARTICULO,
        SUM(S.STOCK) AS STOCK
    FROM STOCKS S
    WHERE S.CODALMACEN IN ('1','2','3','50')
    GROUP BY S.CODALMACEN, S.CODARTICULO
),
BasePairs AS (       -- conjunto base: donde hay stock o hubo ventas
    SELECT CODALMACEN, CODARTICULO FROM StockAgg
    UNION
    SELECT CODALMACEN, CODARTICULO FROM VentasDetalle
),
VentasPrevias AS (   -- si lo necesitas para tu flag NUEVO/EXISTENTE
    SELECT DISTINCT AL.CODARTICULO
    FROM ALBVENTALIN AL
    INNER JOIN ALBVENTACAB AC
        ON AL.NUMSERIE = AC.NUMSERIE
       AND AL.NUMALBARAN = AC.NUMALBARAN
       AND AL.N = AC.N
    WHERE TRY_CONVERT(date, AC.FECHA, 105)  < '{fecha_inicio}'
      AND AC.TIPODOC IN ('13','82','83')
)
SELECT
    AR.CODARTICULO                    AS [Código],
    DP.DESCRIPCION                    AS [Departamento],
    SC.DESCRIPCION                    AS [Sección],
    FM.DESCRIPCION                    AS [Familia],
    SF.DESCRIPCION                    AS [SubFamilia],
    MC.DESCRIPCION                    AS [Marca],
    AR.DESCRIPCION                    AS [Descripción],
    AR.DESCATALOGADO                  AS [Descat],
    AR.TIPO                           AS [Tipo],
    AR.REFPROVEEDOR                   AS [Referencia],
    ACL.CLASIFICACION,
    ACL.CLASIFICACION2,
    ACL.CLASIFICACION3,
    ACL.CLASIFICACION5,
    0                                   AS [Unidades-compras],
   COALESCE(CAST(VPA.Unidad  AS DECIMAL(18,2)), 0) AS [Unidades],       -- 0 si no hay ventas
    0                                   AS [Coste],
    0                                   AS [Beneficio],
    COALESCE(CAST(VPA.Importe AS DECIMAL(18,2)), 0) AS [IMPORTE],        -- 0 si no hay ventas
    0                                   AS [%S/V],
    COALESCE(CAST(S.STOCK     AS DECIMAL(18,3)), 0) AS [StockActual],    -- stock real del almacén
    0                                   AS [Valoración Stock Actual],
    ISNULL(A.NOMBREALMACEN, '') AS [Almacen],
    CASE 
        WHEN VPA.CODARTICULO IS NOT NULL AND VP.CODARTICULO IS NULL THEN 1
        ELSE 0
    END                                AS EsNuevo,
    CASE 
        WHEN VPA.CODARTICULO IS NOT NULL AND VP.CODARTICULO IS NULL THEN 'NUEVO'
        ELSE 'EXISTENTE'
    END                                AS EstadoNuevo
FROM BasePairs BP
JOIN ARTICULOS AR 
    ON AR.CODARTICULO = BP.CODARTICULO
JOIN ARTICULOSCAMPOSLIBRES ACL 
    ON AR.CODARTICULO = ACL.CODARTICULO
LEFT JOIN DEPARTAMENTO DP 
    ON AR.DPTO = DP.NUMDPTO
LEFT JOIN SECCIONES SC 
    ON AR.SECCION = SC.NUMSECCION AND DP.NUMDPTO = SC.NUMDPTO
LEFT JOIN FAMILIAS FM 
    ON DP.NUMDPTO = FM.NUMDPTO 
   AND SC.NUMSECCION = FM.NUMSECCION 
   AND AR.FAMILIA = FM.NUMFAMILIA
LEFT JOIN SUBFAMILIAS SF
    ON AR.DPTO = SF.NUMDPTO 
   AND AR.SECCION = SF.NUMSECCION 
   AND AR.FAMILIA = SF.NUMFAMILIA 
   AND AR.SUBFAMILIA = SF.NUMSUBFAMILIA
LEFT JOIN MARCA MC 
    ON AR.MARCA = MC.CODMARCA
LEFT JOIN VentasDetalle VPA 
    ON BP.CODARTICULO = VPA.CODARTICULO
   AND BP.CODALMACEN  = VPA.CODALMACEN
LEFT JOIN StockAgg S 
    ON BP.CODARTICULO = S.CODARTICULO
   AND BP.CODALMACEN  = S.CODALMACEN
LEFT JOIN ALMACEN A 
    ON A.CODALMACEN = BP.CODALMACEN
LEFT JOIN VentasPrevias VP
    ON AR.CODARTICULO = VP.CODARTICULO
ORDER BY A.NOMBREALMACEN;
"""

    # Ejecutar y cargar datos
    df = ejecutar_consulta(conexion, consulta)
    if df is None:
        return f"Error ejecutando consulta en Proceso #{proceso.pk}"

    # Bulk create de artículos temporales
    articulos = []
    for _, row in df.iterrows():
        articulos.append(ArticuloClasificacionTemporal(
            proceso=proceso,
            codigo=row['Código'],
            departamento=row['Departamento'],
            seccion=row['Sección'],
            familia=row['Familia'],
            subfamilia=row['SubFamilia'],
            marca=row['Marca'],
            descripcion=row['Descripción'],
            descat=row['Descat'],
            tipo=row['Tipo'],
            referencia=row['Referencia'],
            clasificacion=row['CLASIFICACION'],
            clasificacion2=row['CLASIFICACION2'],
            clasificacion3=row['CLASIFICACION3'],
            clasificacion5=row['CLASIFICACION5'],
            unidades_compras=0,
            unidades=row['Unidades'] or 0,
            coste='0',
            beneficio='0',
            importe=row['IMPORTE'] or 0 ,
            porcentaje_sv='0',
            stock_actual=row['StockActual'],
            valoracion_stock_actual='0',
            almacen=row['Almacen'],
            estado_nuevo=row['EstadoNuevo'],
        ))
    ArticuloClasificacionTemporal.objects.bulk_create(articulos)
    # Cambia el estado a 'procesado' al finalizar correctamente
    proceso.estado = 'extraccion'
    proceso.save(update_fields=['estado'])
    procesar_clasificacion(proceso= proceso)
    notificar_proceso_finalizado(proceso, len(articulos))
    return f"Proceso #{proceso.pk} completado: {len(articulos)} artículos cargados"

@shared_task(queue="cola_descuentos")
def actualizar_clasificaciones_en_icg(proceso_id):
    from appMercaSur.conect import conectar_sql_server, ejecutar_consulta_simple
    from .models import ArticuloClasificacionFinal, ProcesoClasificacion

    # Recuperar el objeto proceso por ID
    try:
        proceso = ProcesoClasificacion.objects.get(pk=proceso_id)
    except ProcesoClasificacion.DoesNotExist:
        raise Exception(f"ProcesoClasificacion con id={proceso_id} no existe.")

    conexion = conectar_sql_server()
    if not conexion:
        raise Exception("No fue posible conectar a ICG.")

    articulos = ArticuloClasificacionFinal.objects.filter(proceso=proceso)
    count = 0
    errores = []

    for art in articulos:
        try:
            campo = get_campo_clasificacion_por_almacen(art.almacen)
            if not campo:
                art.estado_accion = "ERROR"
                art.mensaje_accion = f"Almacén no reconocido: {art.almacen}"
                art.save(update_fields=["estado_accion", "mensaje_accion"])
                errores.append(f"{art.codigo}: Almacén no reconocido")
                continue

            sql = f"""
            UPDATE ARTICULOSCAMPOSLIBRES
            SET {campo} = ?
            WHERE CODARTICULO = ?
            """
            params = [art.nueva_clasificacion, art.codigo]
            if art.resultado_validacion == False:
                ejecutar_consulta_simple(conexion, sql, params)

                art.estado_accion = "ACTUALIZADO"
                art.mensaje_accion = "Clasificación actualizada correctamente"
                art.save(update_fields=["estado_accion", "mensaje_accion"])
                count += 1
            else:
                art.estado_accion = "VALIDADO"
                art.mensaje_accion = "Clasificación validada, no se actualiza"
                art.save(update_fields=["estado_accion", "mensaje_accion"])
                count += 1

        except Exception as e:
            art.estado_accion = "ERROR"
            art.mensaje_accion = str(e)
            art.save(update_fields=["estado_accion", "mensaje_accion"])
            errores.append(f"{art.codigo}: {e}")
    proceso.estado = 'actualizado'
    proceso.save()
    notificar_proceso_con_excel(proceso, count)
    return count, "<br>".join(errores)


"""
select  a.CODARTICULO,
a.REFPROVEEDOR,
a2.CLASIFICACION,
a2.CLASIFICACION2,
a2.CLASIFICACION3,
a2.CLASIFICACION5,
a.DESCATALOGADO,
sum(s.STOCK)
from ARTICULOS a 
inner join ARTICULOSCAMPOSLIBRES a2  on a2.CODARTICULO = a.CODARTICULO
inner join STOCKS s on s.CODARTICULO = a.CODARTICULO and s.CODALMACEN in ('1','2','3','50')
where a2.CLASIFICACION = 'I' AND
a2.CLASIFICACION2 = 'I' AND
a2.CLASIFICACION3 = 'I' AND
a2.CLASIFICACION5 = 'I' AND
a.DESCATALOGADO  = 'F' and
(s.STOCK < 0  or s.STOCK = 0)
GROUP by a.CODARTICULO,
a.REFPROVEEDOR,
a2.CLASIFICACION,
a2.CLASIFICACION2,
a2.CLASIFICACION3,
a2.CLASIFICACION5,
a.DESCATALOGADO
"""