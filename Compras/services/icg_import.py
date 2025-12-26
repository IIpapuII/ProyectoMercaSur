from django.utils import timezone
from ..models import SugeridoLote, SugeridoLinea
from django.contrib.auth import get_user_model
from appMercaSur.conect import conectar_sql_server, ejecutar_consulta
from django.db import transaction
from django.utils import timezone
from django.contrib.auth import get_user_model
from django.conf import settings
import pandas as pd
from decimal import Decimal

def import_data_sugerido_inventario(user_id: int | None = None, marcas: list[str] | str | None = None, lote_id: int | None = None, provedor:str | None =None) -> str:
    """
    Importa datos desde ICG y genera líneas de sugerido.
    Si se pasa lote_id, usa ese SugeridoLote existente (no crea uno nuevo).
    Caso contrario crea un lote nuevo basado en timestamp.
    
    Args:
        marcas: Lista de nombres de marcas o una sola marca (string). Si es None, importa todas las marcas asignadas.
    """
    # Normalizar marcas a lista
    if marcas is None:
        marcas_list = []
    elif isinstance(marcas, str):
        marcas_list = [marcas] if marcas else []
    else:
        marcas_list = list(marcas)
    
    print(f"Importando datos ICG para marcas={marcas_list}, proveedor={provedor}, lote_id={lote_id}, user_id={user_id}")
    # ------------------------ Helpers internos ------------------------
    def _safe_int(val, default=0):
        try:
            if val is None:
                return default
            if isinstance(val, bool):
                return int(val)
            # Convertir a string primero para detectar 'nan'
            str_val = str(val).lower().strip()
            if str_val in ['nan', 'null', 'none', '', 'inf', '-inf']:
                return default
            return int(float(val))
        except (ValueError, TypeError, OverflowError):
            return default

    def _safe_float(val, default=0.0):
        try:
            if val is None:
                return default
            # Convertir a string primero para detectar 'nan'
            str_val = str(val).lower().strip()
            if str_val in ['nan', 'null', 'none', '', 'inf', '-inf']:
                return default
            converted = float(val)
            # Verificar si es NaN usando math.isnan o comparación consigo mismo
            if converted != converted:  # NaN != NaN es True
                return default
            return converted
        except (ValueError, TypeError, OverflowError):
            return default

    # NUEVO: asegurar cast a string con strip sin fallar en int/None
    def _safe_str(val, default=""):
        try:
            if val is None:
                return default
            str_val = str(val).strip()
            if str_val.lower() in ['nan', 'null', 'none', '']:
                return default
            return str_val
        except Exception:
            return default

    def _resolve_usuario(uid: int | None):
        User = get_user_model()
        if uid is not None:
            try:
                return User.objects.get(pk=uid)
            except User.DoesNotExist:
                raise ValueError(f"El usuario con id={uid} no existe.")

        system_id = getattr(settings, "SYSTEM_USER_ID", None)
        if system_id is not None:
            try:
                return User.objects.get(pk=system_id)
            except User.DoesNotExist:
                pass

        try:
            return User.objects.get(username="system")
        except User.DoesNotExist:
            pass

        su = User.objects.filter(is_superuser=True).order_by("id").first()
        if su:
            return su

        raise ValueError(
            "No se pudo resolver un usuario para 'creado_por'. "
            "Pasa user_id o define settings.SYSTEM_USER_ID, "
            "o crea un usuario 'system' o un superuser."
        )

    def _ensure_catalogo_by_nombre(ModelClass, nombres: set[str], defaults: dict | None = None) -> dict[str, int]:
        """
        Garantiza que existan registros para todos los 'nombres' (campo 'nombre').
        Retorna: {nombre: id}
        """
        if not nombres:
            return {}

        clean = {str(n).strip() for n in nombres if str(n).strip()}
        if not clean:
            return {}

        existing = dict(
            ModelClass.objects.filter(nombre__in=list(clean)).values_list("nombre", "id")
        )

        missing = [n for n in clean if n not in existing]
        if missing:
            field_names = {f.name for f in ModelClass._meta.get_fields() if hasattr(f, "attname")}
            new_objs = []
            for n in missing:
                kwargs = {"nombre": n}
                if defaults:
                    for k, v in defaults.items():
                        if k in field_names:
                            kwargs.setdefault(k, v)
                new_objs.append(ModelClass(**kwargs))
            if new_objs:
                # Evita choque por unique en concurrencia
                ModelClass.objects.bulk_create(new_objs, ignore_conflicts=True)

            existing = dict(
                ModelClass.objects.filter(nombre__in=list(clean)).values_list("nombre", "id")
            )

        return existing

    # ------------------------ Inicio del proceso ------------------------
    usuario = _resolve_usuario(user_id)
    now = timezone.localtime(timezone.now())

    if lote_id:
        try:
            proceso = SugeridoLote.objects.get(pk=lote_id)
            creado = False
        except SugeridoLote.DoesNotExist:
            return f"Lote con id={lote_id} no existe."
    else:
        nombre_lote = f"Lote {now.strftime('%Y-%m-%d %H:%M:%S')}"
        proceso, creado = SugeridoLote.objects.get_or_create(
            nombre=nombre_lote,
            defaults={
                "fecha_extraccion": now,
                "creado_por": usuario,
            },
        )

    # Si no se creó uno nuevo, se puede optar por actualizar el usuario/fecha del lote existente
    if not creado:
        # Reasigna usuario/fecha si quieres, o déjalo así para idempotencia
        pass

    # Intenta marcar estado inicial (si existe el campo)
    try:
        if getattr(proceso, "estado", None) is not None and not getattr(proceso, "estado"):
            proceso.estado = "PENDIENTE"
            proceso.save(update_fields=["estado"])
    except Exception:
        pass

    # ------------------------ Conexión y consulta ------------------------
    conexion = conectar_sql_server()
    if conexion is None or isinstance(conexion, str):
        # No cambies estado del SugeridoLote aquí; solo retorna mensaje de error
        try:
            setattr(proceso, "estado", "FALLIDO")
            proceso.save(update_fields=["estado"])
        except Exception:
            pass
        extra = f" Detalle: {conexion}" if isinstance(conexion, str) else ""
        return f"Fallo de conexión a ICG en Proceso #{proceso.pk}.{extra}"

    consulta = """
WITH AlmacenesSel AS (
    SELECT CODALMACEN, NOMBREALMACEN
    FROM ALMACEN
    WHERE CODALMACEN IN ('1','2','3','50')
),
Base AS (
    SELECT
        a.CODALMACEN                               AS cod_almacen,
        a.NOMBREALMACEN                            AS nombre_almacen,
        AR.CODARTICULO                             AS codigo,
        AR.REFPROVEEDOR                            AS referencia,
        DP.DESCRIPCION                             AS departamento,
        SC.DESCRIPCION                             AS seccion,
        FM.DESCRIPCION                             AS familia,
        SF.DESCRIPCION                             AS subfamilia,
        MC.DESCRIPCION                             AS marca,
        p.NOMPROVEEDOR                             AS proveedor,
        AR.DESCRIPCION                             AS descripcion,
        COALESCE(S.STOCK, 0)                       AS stock_actual,
        COALESCE(S.MINIMO, 0)                      AS stock_minimo,
        COALESCE(S.MAXIMO, 0)                      AS stock_maximo,
        AR.UNID1C                                  AS uds_compra_base,
        AR.UNID2C                                  AS uds_compra_mult,
                COALESCE(
            NULLIF(c.ULTIMOCOSTE, 0),
            (SELECT MAX(c2.ULTIMOCOSTE)
             FROM COSTESPORALMACEN c2
             WHERE c2.CODARTICULO = AR.CODARTICULO
               AND c2.ULTIMOCOSTE IS NOT NULL
               AND c2.ULTIMOCOSTE <> 0)
        )                                           AS ultimo_costo,
        AR.TIPO                                    AS tipo,
        CASE 
            WHEN a.NOMBREALMACEN = 'MERCASUR CALDAS'    THEN ACL.CLASIFICACION
            WHEN a.NOMBREALMACEN = 'MERCASUR CENTRO'    THEN ACL.CLASIFICACION2
            WHEN a.NOMBREALMACEN = 'MERCASUR CABECERA'  THEN ACL.CLASIFICACION3
            WHEN a.NOMBREALMACEN = 'MERCASUR SOTOMAYOR' THEN ACL.CLASIFICACION5
            ELSE NULL
        END                                         AS clasificacion,
        (
            SELECT TOP (1) lin.DTO
            FROM PEDCOMPRACAB cab
            INNER JOIN PEDCOMPRALIN lin
                ON lin.NUMPEDIDO = cab.NUMPEDIDO
               AND lin.NUMSERIE  = cab.NUMSERIE
            WHERE lin.CODARTICULO = AR.CODARTICULO
            ORDER BY TRY_CONVERT(date, cab.FECHAPEDIDO, 105) DESC
        )                                           AS ultimodescuento,
        p.CODPROVEEDOR                              AS CodProveedor,
        (SELECT i.IVA FROM IMPUESTOS i WHERE i.TIPOIVA = AR.IMPUESTOCOMPRA) AS iva,
        r.PRINCIPAL                                 AS proveedorPrincipal
    FROM ARTICULOS AR
    INNER JOIN ARTICULOSCAMPOSLIBRES ACL 
        ON AR.CODARTICULO = ACL.CODARTICULO
    LEFT  JOIN DEPARTAMENTO DP 
        ON AR.DPTO = DP.NUMDPTO
    LEFT  JOIN SECCIONES SC 
        ON AR.SECCION = SC.NUMSECCION AND DP.NUMDPTO = SC.NUMDPTO
    LEFT  JOIN FAMILIAS FM 
        ON DP.NUMDPTO = FM.NUMDPTO AND SC.NUMSECCION = FM.NUMSECCION AND AR.FAMILIA = FM.NUMFAMILIA
    LEFT  JOIN SUBFAMILIAS SF 
        ON AR.DPTO = SF.NUMDPTO AND AR.SECCION = SF.NUMSECCION AND AR.FAMILIA = SF.NUMFAMILIA AND AR.SUBFAMILIA = SF.NUMSUBFAMILIA
    LEFT  JOIN MARCA MC 
        ON AR.MARCA = MC.CODMARCA
    /* mostrar TODAS las bodegas seleccionadas */
    CROSS JOIN AlmacenesSel a
    LEFT  JOIN STOCKS S 
        ON AR.CODARTICULO = S.CODARTICULO
       AND S.CODALMACEN   = a.CODALMACEN
    LEFT  JOIN COSTESPORALMACEN c 
        ON c.CODALMACEN = a.CODALMACEN 
       AND c.CODARTICULO = AR.CODARTICULO
    INNER JOIN REFERENCIASPROV r 
        ON r.CODARTICULO = AR.CODARTICULO
    INNER JOIN PROVEEDORES p  
        ON p.CODPROVEEDOR = r.CODPROVEEDOR
    WHERE AR.DESCATALOGADO = 'F'
      """
    if marcas_list:
        # Escapar comillas simples en cada marca
        marcas_escaped = [m.replace("'", "''") for m in marcas_list]
        marcas_str = "', '".join(marcas_escaped)
        consulta += f"      AND MC.DESCRIPCION IN ('{marcas_str}')\n"
    if provedor:
        consulta += f"      AND p.NOMPROVEEDOR = '{provedor.replace("'", "''")}'\n"
    consulta += """
),
Calculos AS (
    SELECT
        b.*,
        /* embalaje mínimo 1 si vienen ceros */
        COALESCE(NULLIF(b.uds_compra_base, 0), 1) * COALESCE(NULLIF(b.uds_compra_mult, 0), 1) AS embalaje,
        CASE 
            WHEN (b.stock_maximo - b.stock_actual) < 0 THEN CAST(0 AS DECIMAL(18,4))
            ELSE CAST(b.stock_maximo - b.stock_actual AS DECIMAL(18,4))
        END AS diff_sin_redondeo,
        CASE 
            WHEN UPPER(LTRIM(RTRIM(b.nombre_almacen))) = 'MERCASUR CALDAS' 
                THEN CAST(1.30 AS DECIMAL(10,4))
            ELSE CAST(1.50 AS DECIMAL(10,4))
        END AS factor_almacen
    FROM Base b
),
Redondeo AS (
    SELECT
        c.*,
        CASE WHEN c.embalaje <= 0 THEN 1 ELSE c.embalaje END AS embalaje_safe,
        FLOOR( c.diff_sin_redondeo / NULLIF(c.embalaje,0) ) AS paquetes_floor,
        (c.diff_sin_redondeo / NULLIF(c.embalaje,0)) - FLOOR(c.diff_sin_redondeo / NULLIF(c.embalaje,0)) AS fraccion_paquete
    FROM Calculos c
),
Final AS (
    SELECT
        r.*,
        /* reglas de redondeo por bodega para el sugerido_base */
        CASE 
            WHEN r.diff_sin_redondeo <= 0 OR r.embalaje_safe <= 0 THEN CAST(0 AS DECIMAL(18,4))
            /* NUEVA REGLA: Si diff_sin_redondeo < embalaje_safe, retornar 0 */
            WHEN r.diff_sin_redondeo < r.embalaje_safe THEN CAST(0 AS DECIMAL(18,4))
            WHEN r.cod_almacen IN ('1','2')
                THEN CEILING( r.diff_sin_redondeo / r.embalaje_safe ) * r.embalaje_safe
            WHEN r.cod_almacen IN ('3','50')
                THEN CASE 
                        WHEN r.fraccion_paquete > 0.3 
                             THEN (r.paquetes_floor + 1) * r.embalaje_safe
                        ELSE r.paquetes_floor * r.embalaje_safe
                     END
            ELSE r.diff_sin_redondeo
        END AS sugerido_base
    FROM Redondeo r
)
SELECT
    cod_almacen                                AS CODALMACEN,
    nombre_almacen                             AS Almacen,
    codigo                                     AS [Código],
    referencia                                 AS [Referencia],
    departamento                               AS [Departamento],
    seccion                                    AS [Sección],
    familia                                    AS [Familia],
    subfamilia                                 AS [SubFamilia],
    marca                                      AS [Marca],
    proveedor                                  AS [Proveedor],
    descripcion                                AS [Descripción],
    stock_actual                               AS [StockActual],
    stock_minimo                               AS [StockMinimo],
    stock_maximo                               AS [StockMaximo],
    uds_compra_base                            AS [UdsCompraBase],
    uds_compra_mult                            AS [UdsCompraMult],
    embalaje_safe                              AS [Embalaje],
    ultimo_costo                               AS [UltimoCosto],
    tipo                                       AS [Tipo],
    clasificacion                              AS [Clasificacion],
    CAST(sugerido_base AS DECIMAL(18,4))       AS [SugeridoBase],
    factor_almacen                             AS [Factor],
    CASE 
        WHEN sugerido_base <= 0 THEN 0
        WHEN embalaje_safe <= 0 THEN CEILING(CAST(sugerido_base AS DECIMAL(18,4)) * factor_almacen)
        ELSE CEILING( (CAST(sugerido_base AS DECIMAL(18,4)) * factor_almacen) / CAST(embalaje_safe AS DECIMAL(18,4)) ) * embalaje_safe
    END                                         AS [Sugerido],
    CASE 
        WHEN sugerido_base <= 0 OR embalaje_safe = 0 THEN 0
        ELSE (
            CEILING( (CAST(sugerido_base AS DECIMAL(18,4)) * factor_almacen) / CAST(embalaje_safe AS DECIMAL(18,4)) )
        )
    END                                         AS [Cajas],
    CASE 
        WHEN sugerido_base <= 0 THEN 0
        WHEN embalaje_safe <= 0 THEN CEILING(CAST(sugerido_base AS DECIMAL(18,4)) * factor_almacen) * ultimo_costo
        ELSE CEILING( (CAST(sugerido_base AS DECIMAL(18,4)) * factor_almacen) / CAST(embalaje_safe AS DECIMAL(18,4)) ) * embalaje_safe * ultimo_costo
    END                                         AS [CostoLinea],
    ultimodescuento                             AS [UltimoDescuentoPedido],
    CodProveedor                                AS [CodProveedor],
    iva                                         AS [IVA],
    CASE WHEN diff_sin_redondeo <= 0 THEN 1 ELSE 0 END AS EsInformativa,
    proveedorPrincipal
FROM Final
ORDER BY nombre_almacen, codigo;
"""

    try:
        # Tu ejecutar_consulta acepta ambos órdenes; uso (sql, conexion).
        df = ejecutar_consulta( conexion ,consulta)
    finally:
        try:
            if hasattr(conexion, "close"):
                conexion.close()
        except Exception:
            pass

    if df is None:
        # No cambies estado del SugeridoLote aquí
        return f"Error ejecutando consulta en Proceso #{proceso.pk}"

    # ------------------------ Resolver modelos de FK ------------------------
    proveedor_field = SugeridoLinea._meta.get_field("proveedor")
    marca_field = SugeridoLinea._meta.get_field("marca")
    ProveedorModel = proveedor_field.remote_field.model
    MarcaModel = marca_field.remote_field.model

    # ------------------------ Construir mapas y crear faltantes ------------------------
    proveedores = set()
    marcas = set()
    # NUEVO: mapa de nombre proveedor -> CodProveedor (ICG)
    prov_cod_map = {}
    for _, row in df.iterrows():
        p = _safe_str(row.get("Proveedor"))
        m = _safe_str(row.get("Marca"))
        if p:
            proveedores.add(p)
            # tomar primer código no vacío visto
            codp = _safe_str(row.get("CodProveedor"))
            if codp and p not in prov_cod_map:
                prov_cod_map[p] = codp
        if m:
            marcas.add(m)

    # Siempre tener un proveedor por defecto para huecos
    default_prov_name = "DESCONOCIDO (ICG)"
    proveedores.add(default_prov_name)

    prov_defaults = {
        "nit": "",
        "email_contacto": "",
        "activo": True,
        "cod_icg": None,
    }
    prov_map = _ensure_catalogo_by_nombre(ProveedorModel, proveedores, prov_defaults)
    marca_map = _ensure_catalogo_by_nombre(MarcaModel, marcas, defaults=None)
    default_prov_id = prov_map.get(default_prov_name)

    # NUEVO: asignar/actualizar cod_icg a todos los proveedores con código disponible
    if prov_cod_map:
        name_to_id = {name: pid for name, pid in prov_map.items() if name in prov_cod_map}
        if name_to_id:
            objs = ProveedorModel.objects.filter(id__in=name_to_id.values()).only("id", "cod_icg")
            id_to_obj = {o.id: o for o in objs}
            to_update = []
            for name, pid in name_to_id.items():
                obj = id_to_obj.get(pid)
                code = _safe_str(prov_cod_map.get(name))
                if not obj or not code:
                    continue
                actual = _safe_str(getattr(obj, "cod_icg", ""))
                if actual != code:
                    obj.cod_icg = code
                    to_update.append(obj)
            if to_update:
                ProveedorModel.objects.bulk_update(to_update, ["cod_icg"])

    # ------------------------ Obtener KPIs de inventario ------------------------
    # Extraer marca_ids y almacenes únicos del DataFrame principal
    marca_names = set(df['Marca'].dropna().unique())
    almacenes_df = set(df['CODALMACEN'].dropna().astype(str).unique())
    
    # Mapear nombres de marca a IDs de ICG (necesitas ajustar este mapeo según tu BD)
    # Por ahora, usamos los valores por defecto
    df_kpis = obtener_kpis_inventario_icg(
        marca_ids=[4, 7, 12],  # Ajusta según las marcas que estés importando
        almacenes=list(almacenes_df) if almacenes_df else ['1','2','3','50']
    )
    
    # Crear diccionario de búsqueda de KPIs por (almacen, articulo)
    kpis_dict = {}
    if df_kpis is not None and not df_kpis.empty:
        for _, kpi_row in df_kpis.iterrows():
            key = (str(kpi_row['CodAlmacen']), str(kpi_row['CodigoArticulo']))
            kpis_dict[key] = {
                'valor_inventario': _safe_float(kpi_row.get('ValorInventario'), 0.0),
                'unidades_vendidas_90d': _safe_float(kpi_row.get('UnidadesVendidas_90d'), 0.0),
                'venta_diaria_promedio': _safe_float(kpi_row.get('VentaDiariaPromedio'), 0.0),
                'dias_inventario': _safe_float(kpi_row.get('DiasInventario'), None) if kpi_row.get('DiasInventario') is not None else None,
            }
    
    # ------------------------ Evitar duplicados por lote ------------------------
    existentes = set(
        SugeridoLinea.objects.filter(lote=proceso)
        .values_list("cod_almacen", "codigo_articulo")
    )

    registros = []
    insertados = 0
    omitidos = 0
    errores = 0

    for _, row in df.iterrows():
        cod_alm = _safe_str(row.get("CODALMACEN"))
        cod_art = _safe_str(row.get("Código"))

        # Validar que los campos esenciales no estén vacíos
        if not cod_alm or not cod_art:
            errores += 1
            continue

        if (cod_alm, cod_art) in existentes:
            omitidos += 1
            continue
        existentes.add((cod_alm, cod_art))

        prov_name = _safe_str(row.get("Proveedor"))
        marca_name = _safe_str(row.get("Marca"))

        proveedor_id = prov_map.get(prov_name) or default_prov_id
        marca_id = marca_map.get(marca_name) if marca_name else None

        # Validar campos numéricos críticos
        ultimo_costo = _safe_float(row.get("UltimoCosto"))
        factor_almacen = _safe_float(row.get("Factor"), 1.0)
        
        # NUEVA VALIDACIÓN: Obtener clasificación y forzar sugeridos a 0 SOLO si es I
        clasificacion_raw = _safe_str(row.get("Clasificacion"))
        clasificacion_upper = clasificacion_raw.upper() if clasificacion_raw else ""
        
        # CAMBIO: Solo forzar a 0 si clasificación es I (NO C)
        if clasificacion_upper == 'I':
            sugerido_base_val = 0
            nuevo_sugerido_prov_val = 0
            sugerido_interno_val = 0
            sugerido_calculado_val = 0
            cajas_calculadas_val = 0.0
            costo_linea_val = 0.0
            es_informativa_val = True
        else:
            sugerido_base_val = _safe_int(row.get("SugeridoBase"))
            nuevo_sugerido_prov_val = _safe_int(row.get("SugeridoBase"))
            sugerido_interno_val = _safe_int(row.get("SugeridoBase"))
            sugerido_calculado_val = _safe_int(row.get("Sugerido"))
            cajas_calculadas_val = _safe_float(row.get("Cajas"))
            costo_linea_val = _safe_float(row.get("CostoLinea"))
            # Marcar como informativa si sugerido_base es 0 pero diff > 0
            es_informativa_val = bool(_safe_int(row.get("EsInformativa"), 0))
            
            # NUEVO: Para clasificación C, nuevo_sugerido_prov debe ser igual a sugerido_interno
            if clasificacion_upper == 'C':
                nuevo_sugerido_prov_val = sugerido_interno_val

        try:
            # Garantizar que descripcion nunca sea None o vacía
            descripcion = _safe_str(row.get("Descripción")) or "SIN DESCRIPCIÓN"
            
            # Obtener KPIs del diccionario
            kpi_key = (cod_alm, cod_art)
            kpis = kpis_dict.get(kpi_key, {
                'valor_inventario': 0.0,
                'unidades_vendidas_90d': 0.0,
                'venta_diaria_promedio': 0.0,
                'dias_inventario': None,
            })
            
            registro = SugeridoLinea(
                lote=proceso,
                cod_almacen=cod_alm,
                nombre_almacen=_safe_str(row.get("Almacen")) or None,
                codigo_articulo=cod_art,
                referencia=_safe_str(row.get("Referencia")) or None,
                departamento=_safe_str(row.get("Departamento")) or None,
                seccion=_safe_str(row.get("Sección")) or None,
                familia=_safe_str(row.get("Familia")) or None,
                subfamilia=_safe_str(row.get("SubFamilia")) or None,
                proveedor_id=proveedor_id,
                marca_id=marca_id,
                descripcion=descripcion,
                stock_actual=_safe_int(row.get("StockActual")),
                stock_minimo=_safe_int(row.get("StockMinimo")),
                stock_maximo=_safe_int(row.get("StockMaximo")),
                uds_compra_base=_safe_int(row.get("UdsCompraBase"), 1),
                uds_compra_mult=_safe_int(row.get("UdsCompraMult"), 1),
                embalaje=_safe_int(row.get("Embalaje"), 1),
                ultimo_costo=ultimo_costo,
                tipo=_safe_str(row.get("Tipo")) or None,
                clasificacion=clasificacion_raw or None,
                sugerido_base=sugerido_base_val,
                nuevo_sugerido_prov=nuevo_sugerido_prov_val,
                sugerido_interno=sugerido_interno_val,
                factor_almacen=factor_almacen,
                sugerido_calculado=sugerido_calculado_val,
                cajas_calculadas=cajas_calculadas_val,
                costo_linea=costo_linea_val,
                descuento_prov_pct=_safe_float(row.get("UltimoDescuentoPedido")),
                cod_proveedor=_safe_str(row.get("CodProveedor")) or None,
                IVA=_safe_float(row.get("IVA"), 0.0),
                es_informativa=es_informativa_val,
                Proveedor_principal=_safe_str(row.get("proveedorPrincipal")),
                # Nuevos campos de KPIs
                valor_inventario=Decimal(str(kpis['valor_inventario'])),
                unidades_vendidas_90d=Decimal(str(kpis['unidades_vendidas_90d'])),
                venta_diaria_promedio=Decimal(str(kpis['venta_diaria_promedio'])),
                dias_inventario=Decimal(str(kpis['dias_inventario'])) if kpis['dias_inventario'] is not None else None,
                clasificacion_original=clasificacion_raw or None,
            )
            registros.append(registro)
            insertados += 1
        except Exception as e:
            print(f"Error creando registro para {cod_alm}-{cod_art}: {e}")
            errores += 1
            continue

    with transaction.atomic():
        if registros:
            SugeridoLinea.objects.bulk_create(registros, batch_size=1000)

    mensaje_final = (
        f"Proceso #{proceso.pk} -> líneas nuevas: {insertados}, "
        f"omitidas (duplicadas en lote): {omitidos}"
    )
    if errores > 0:
        mensaje_final += f", errores: {errores}"
    
    return mensaje_final + "."


def obtener_kpis_por_codigos(almacen_codigos_map: dict[str, list[str]]) -> pd.DataFrame | None:
    """
    Obtiene KPIs para una lista específica de artículos por almacén.
    
    Args:
        almacen_codigos_map: Dict { 'cod_almacen': ['cod_art1', 'cod_art2', ...], ... }
    """
    if not almacen_codigos_map:
        return None
        
    dfs = []
    conexion = conectar_sql_server()
    if conexion is None or isinstance(conexion, str):
        print(f"Error conectando a ICG (actualizar KPIs): {conexion}")
        return None
        
    try:
        for cod_alm, codigos in almacen_codigos_map.items():
            if not codigos:
                continue
            
            # Procesar en lotes de 2000 códigos para no exceder límites SQL
            batch_size = 2000
            for i in range(0, len(codigos), batch_size):
                batch_codigos = codigos[i:i + batch_size]
                
                codigos_str = "', '".join(c.replace("'", "''") for c in batch_codigos)
                
                consulta = f"""
                ;WITH VentasUnidades AS (
                    SELECT
                        AL.CODALMACEN,
                        AL.CODARTICULO,
                        SUM(AL.UNID1) AS unidades_vendidas
                    FROM ALBVENTALIN AL
                    INNER JOIN ALBVENTACAB AC
                        ON AC.NUMSERIE   = AL.NUMSERIE
                       AND AC.NUMALBARAN = AL.NUMALBARAN
                    WHERE
                        AC.FECHA >= DATEADD(DAY, -90, CAST(GETDATE() AS DATE))
                        AND AC.FECHA <  DATEADD(DAY, 1,  CAST(GETDATE() AS DATE))
                        AND AC.TIPODOC IN (13, 82, 83)
                        AND AL.CODALMACEN = '{cod_alm}'
                        AND AL.CODARTICULO IN ('{codigos_str}')
                    GROUP BY
                        AL.CODALMACEN,
                        AL.CODARTICULO
                )
                SELECT
                    A.CODARTICULO                              AS CodigoArticulo,
                    S.CODALMACEN                               AS CodAlmacen,
                    S.STOCK                                    AS StockActual,
                    C.ULTIMOCOSTE                              AS UltimoCosto,
                    CAST(S.STOCK * C.ULTIMOCOSTE AS DECIMAL(18,2)) AS ValorInventario,
                    COALESCE(V.unidades_vendidas, 0)           AS UnidadesVendidas_90d,
                    CAST(
                        COALESCE(V.unidades_vendidas, 0) / CAST(90 AS DECIMAL(10,2))
                        AS DECIMAL(18,4)
                    )                                          AS VentaDiariaPromedio,
                    CAST(
                        CASE
                            WHEN V.unidades_vendidas IS NULL OR V.unidades_vendidas = 0
                                THEN NULL
                            ELSE S.STOCK /
                                 (V.unidades_vendidas / CAST(90 AS DECIMAL(10,2)))
                        END
                        AS DECIMAL(18,2)
                    )                                          AS DiasInventario
                FROM ARTICULOS A
                INNER JOIN STOCKS S
                    ON A.CODARTICULO = S.CODARTICULO
                   AND S.CODALMACEN = '{cod_alm}'
                LEFT JOIN COSTESPORALMACEN C
                    ON C.CODARTICULO = A.CODARTICULO
                   AND C.CODALMACEN  = S.CODALMACEN
                LEFT JOIN VentasUnidades V
                    ON V.CODARTICULO = A.CODARTICULO
                   AND V.CODALMACEN  = S.CODALMACEN
                WHERE
                    A.CODARTICULO IN ('{codigos_str}')
                """
                
                df_batch = ejecutar_consulta(conexion, consulta)
                if df_batch is not None and not df_batch.empty:
                    dfs.append(df_batch)
                    
        if dfs:
            return pd.concat(dfs, ignore_index=True)
        return None
        
    finally:
        try:
            conexion.close()
        except:
            pass

def actualizar_kpis_lote(lote_id: int) -> str:
    """
    Actualiza los KPIs (inventario, ventas, etc.) de las líneas existentes en un lote.
    """
    try:
        lote = SugeridoLote.objects.get(pk=lote_id)
    except SugeridoLote.DoesNotExist:
        return f"Lote {lote_id} no existe."

    # Obtener todas las líneas
    lineas = SugeridoLinea.objects.filter(lote=lote)
    if not lineas.exists():
        lote.fecha_actualizacion_kpis = timezone.now()
        lote.save(update_fields=['fecha_actualizacion_kpis'])
        return "Lote sin líneas."

    # Agrupar códigos por almacén
    mapa_consulta = {}
    lineas_map = {} # (cod_alm, cod_art) -> linea_obj
    
    for ln in lineas:
        c_alm = str(ln.cod_almacen)
        c_art = str(ln.codigo_articulo)
        if c_alm not in mapa_consulta:
            mapa_consulta[c_alm] = []
        mapa_consulta[c_alm].append(c_art)
        lineas_map[(c_alm, c_art)] = ln

    # Consultar ICG
    df = obtener_kpis_por_codigos(mapa_consulta)
    
    if df is None or df.empty:
         # Nada que actualizar o error
         # Actualizamos fecha para no reintentar inmediatamente si fue un caso vacio
         lote.fecha_actualizacion_kpis = timezone.now()
         lote.save(update_fields=['fecha_actualizacion_kpis'])
         return "Sin datos devueltos por ICG."

    actualizados = 0
    to_update = []
    
    for _, row in df.iterrows():
        try:
            c_alm = str(row['CodAlmacen'])
            c_art = str(row['CodigoArticulo'])
            
            linea = lineas_map.get((c_alm, c_art))
            if linea:
                # Actualizar campos
                linea.valor_inventario = Decimal(str(row['ValorInventario'] or 0))
                linea.unidades_vendidas_90d = Decimal(str(row['UnidadesVendidas_90d'] or 0))
                linea.venta_diaria_promedio = Decimal(str(row['VentaDiariaPromedio'] or 0))
                
                dias = row['DiasInventario']
                linea.dias_inventario = Decimal(str(dias)) if (dias is not None and pd.notna(dias)) else None
                
                # También actualizamos stock_actual si ha cambiado, ya que afecta KPIs
                # OJO: Cambiar stock puede afectar sugeridos, pero el usuario pidió actualizar KPIs.
                # Se asume que tener el stock real es deseable.
                stock_nuevo = Decimal(str(row['StockActual'] or 0))
                if linea.stock_actual != stock_nuevo:
                    linea.stock_actual = stock_nuevo
                    # Si cambiamos stock, deberíamos recalcular sugeridos? 
                    # Tal vez mejor NO tocar el cálculo base para no romper "foto" del momento, 
                    # pero KPI implica datos en tiempo real.
                    # El usuario dijo "quiero que estos kpi se actualicen".
                    # Dejaremos stock actualizado porque es un KPI fundamental.
                
                to_update.append(linea)
                actualizados += 1
        except Exception as e:
            print(f"Error procesando fila {row}: {e}")

    if to_update:
        # Usamos bulk_update para eficiencia
        fields_to_update = [
            'valor_inventario', 'unidades_vendidas_90d', 
            'venta_diaria_promedio', 'dias_inventario', 'stock_actual'
        ]
        SugeridoLinea.objects.bulk_update(to_update, fields_to_update, batch_size=1000)

    # Actualizar timestamp del lote
    lote.fecha_actualizacion_kpis = timezone.now()
    lote.save(update_fields=['fecha_actualizacion_kpis'])

    return f"KPIs actualizados para {actualizados} líneas."


def obtener_kpis_inventario_icg(marca_ids: list[int] | None = None, almacenes: list[str] | None = None) -> pd.DataFrame | None:
    """
    Obtiene los KPIs de inventario desde ICG:
    - Valor total de inventario por artículo
    - Unidades vendidas en los últimos 90 días
    - Venta diaria promedio
    - Días de inventario
    
    Args:
        marca_ids: Lista de IDs de marca en ICG (ej: [4, 7, 12])
        almacenes: Lista de códigos de almacén (ej: ['1','2','3','50'])
    
    Returns:
        DataFrame con los KPIs o None si hay error
    """
    # Valores por defecto
    if marca_ids is None:
        marca_ids = [4, 7, 12]  # Marcas importadas por defecto
    if almacenes is None:
        almacenes = ['1', '2', '3', '50']
    
    # Construir filtros dinámicos
    marca_filter = ", ".join(map(str, marca_ids))
    almacen_filter = ", ".join(almacenes)
    
    consulta = f"""
;WITH VentasUnidades AS (
    SELECT
        AL.CODALMACEN,
        AL.CODARTICULO,
        SUM(AL.UNID1) AS unidades_vendidas
    FROM ALBVENTALIN AL
    INNER JOIN ALBVENTACAB AC
        ON AC.NUMSERIE   = AL.NUMSERIE
       AND AC.NUMALBARAN = AL.NUMALBARAN
    INNER JOIN ARTICULOS AR
        ON AR.CODARTICULO = AL.CODARTICULO
    WHERE
        AC.FECHA >= DATEADD(DAY, -90, CAST(GETDATE() AS DATE))
        AND AC.FECHA <  DATEADD(DAY, 1,  CAST(GETDATE() AS DATE))
        AND AC.TIPODOC IN (13, 82, 83)
        AND AL.CODALMACEN IN ({almacen_filter})
        AND AR.MARCA IN ({marca_filter})
    GROUP BY
        AL.CODALMACEN,
        AL.CODARTICULO
)
SELECT
    A.CODARTICULO                              AS CodigoArticulo,
    A.DESCRIPCION                              AS DescripcionArticulo,
    M.DESCRIPCION                              AS Marca,
    S.CODALMACEN                               AS CodAlmacen,
    S.STOCK                                    AS StockActual,
    C.ULTIMOCOSTE                              AS UltimoCosto,
    CAST(S.STOCK * C.ULTIMOCOSTE AS DECIMAL(18,2)) AS ValorInventario,
    COALESCE(V.unidades_vendidas, 0)           AS UnidadesVendidas_90d,
    CAST(
        COALESCE(V.unidades_vendidas, 0) / CAST(90 AS DECIMAL(10,2))
        AS DECIMAL(18,4)
    )                                          AS VentaDiariaPromedio,
    CAST(
        CASE
            WHEN V.unidades_vendidas IS NULL OR V.unidades_vendidas = 0
                THEN NULL
            ELSE S.STOCK /
                 (V.unidades_vendidas / CAST(90 AS DECIMAL(10,2)))
        END
        AS DECIMAL(18,2)
    )                                          AS DiasInventario
FROM ARTICULOS A
INNER JOIN MARCA M
    ON A.MARCA = M.CODMARCA
INNER JOIN STOCKS S
    ON A.CODARTICULO = S.CODARTICULO
   AND S.CODALMACEN IN ({almacen_filter})
LEFT JOIN COSTESPORALMACEN C
    ON C.CODARTICULO = A.CODARTICULO
   AND C.CODALMACEN  = S.CODALMACEN
LEFT JOIN VentasUnidades V
    ON V.CODARTICULO = A.CODARTICULO
   AND V.CODALMACEN  = S.CODALMACEN
WHERE
    A.DESCATALOGADO = 'F'
    AND A.MARCA IN ({marca_filter})
ORDER BY
    M.DESCRIPCION,
    A.CODARTICULO;
"""
    
    conexion = conectar_sql_server()
    if conexion is None or isinstance(conexion, str):
        print(f"Error conectando a ICG para KPIs: {conexion}")
        return None
    
    try:
        df = ejecutar_consulta(conexion, consulta)
        return df
    except Exception as e:
        print(f"Error ejecutando consulta de KPIs: {e}")
        return None
    finally:
        try:
            conexion.close()
        except Exception:
            pass


def calcular_kpis_resumen(df_kpis: pd.DataFrame | None) -> dict:
    """
    Calcula KPIs agregados a partir del DataFrame de inventario.
    
    Args:
        df_kpis: DataFrame con los datos de KPIs por artículo
    
    Returns:
        Diccionario con KPIs agregados:
        - valor_total_inventario: Suma total del valor de inventario
        - dias_inventario_promedio: Promedio de días de inventario
        - dias_inventario_mediana: Mediana de días de inventario
        - total_unidades_stock: Total de unidades en stock
        - total_articulos: Cantidad de artículos únicos
    """
    if df_kpis is None or df_kpis.empty:
        return {
            "valor_total_inventario": 0.0,
            "dias_inventario_promedio": None,
            "dias_inventario_mediana": None,
            "total_unidades_stock": 0.0,
            "total_articulos": 0,
        }
    
    # Filtrar días de inventario válidos (no nulos)
    dias_validos = df_kpis[df_kpis['DiasInventario'].notna()]['DiasInventario']
    
    return {
        "valor_total_inventario": float(df_kpis['ValorInventario'].sum()),
        "dias_inventario_promedio": float(dias_validos.mean()) if len(dias_validos) > 0 else None,
        "dias_inventario_mediana": float(dias_validos.median()) if len(dias_validos) > 0 else None,
        "total_unidades_stock": float(df_kpis['StockActual'].sum()),
        "total_articulos": len(df_kpis['CodigoArticulo'].unique()),
    }