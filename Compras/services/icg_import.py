from django.utils import timezone
from ..models import SugeridoLote, SugeridoLinea
from django.contrib.auth import get_user_model
from appMercaSur.conect import conectar_sql_server, ejecutar_consulta
from django.db import transaction
from django.utils import timezone
from django.contrib.auth import get_user_model
from django.conf import settings

def import_data_sugerido_inventario(user_id: int | None = None, marca: str | None = None, lote_id: int | None = None, provedor:str | None =None) -> str:
    """
    Importa datos desde ICG y genera líneas de sugerido.
    Si se pasa lote_id, usa ese SugeridoLote existente (no crea uno nuevo).
    Caso contrario crea un lote nuevo basado en timestamp.
    """
    print(f"Importando datos ICG para marca={marca}, proveedor={provedor}, lote_id={lote_id}, user_id={user_id}")
    # ------------------------ Helpers internos ------------------------
    def _safe_int(val, default=0):
        try:
            if val is None:
                return default
            if isinstance(val, bool):
                return int(val)
            return int(float(val))
        except Exception:
            return default

    def _safe_float(val, default=0.0):
        try:
            if val is None:
                return default
            return float(val)
        except Exception:
            return default

    # NUEVO: asegurar cast a string con strip sin fallar en int/None
    def _safe_str(val, default=""):
        try:
            if val is None:
                return default
            return str(val).strip()
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
WITH Base AS (
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
        S.STOCK                                    AS stock_actual,
        S.MINIMO                                   AS stock_minimo,
        S.MAXIMO                                   AS stock_maximo,
        AR.UNID1C                                  AS uds_compra_base,
        AR.UNID2C                                  AS uds_compra_mult,
        COALESCE(c.ULTIMOCOSTE, 0)                 AS ultimo_costo,
        AR.TIPO                                    AS tipo,
        CASE 
            WHEN a.NOMBREALMACEN = 'MERCASUR CALDAS'    THEN ACL.CLASIFICACION
            WHEN a.NOMBREALMACEN = 'MERCASUR CENTRO'    THEN ACL.CLASIFICACION2
            WHEN a.NOMBREALMACEN = 'MERCASUR CABECERA'  THEN ACL.CLASIFICACION3
            WHEN a.NOMBREALMACEN = 'MERCASUR SOTOMAYOR' THEN ACL.CLASIFICACION5
            ELSE NULL
        END                                         AS clasificacion,
                (
    SELECT
        TOP (1)
        a2.DTO
    FROM
        PEDCOMPRACAB a
    inner JOIN PEDCOMPRALIN a2 ON
        a2.NUMPEDIDO = a.NUMPEDIDO
        AND a2.NUMSERIE = a.NUMSERIE
    where
        a2.CODARTICULO = AR.CODARTICULO 
    ORDER BY
        TRY_CONVERT(date, a.FECHAPEDIDO, 105) DESC) as ultimodescuento,
    p.CODPROVEEDOR as CodProveedor,
	(select i.IVA from IMPUESTOS i where i.TIPOIVA = AR.IMPUESTOCOMPRA ) as iva
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
    LEFT  JOIN STOCKS S 
        ON AR.CODARTICULO = S.CODARTICULO
    INNER JOIN ALMACEN a 
        ON S.CODALMACEN = a.CODALMACEN
    INNER JOIN COSTESPORALMACEN c 
        ON c.CODALMACEN = a.CODALMACEN AND c.CODARTICULO = AR.CODARTICULO 
    INNER JOIN REFERENCIASPROV r 
        ON r.CODARTICULO = AR.CODARTICULO AND r.PRINCIPAL = 'T'
    INNER JOIN PROVEEDORES p  
        ON p.CODPROVEEDOR = r.CODPROVEEDOR 
    WHERE AR.DESCATALOGADO = 'F'
      AND a.CODALMACEN IN ('1','2','3','50')
"""
    if marca:
        consulta += f"      AND MC.DESCRIPCION = '{marca.replace("'", "''")}'\n"
    if provedor:
        consulta += f"      AND p.NOMPROVEEDOR = '{provedor.replace("'", "''")}'\n"
    consulta += """
),
Calculos AS (
    SELECT
        *,
        COALESCE(NULLIF(uds_compra_base, 0), 1) * COALESCE(NULLIF(uds_compra_mult, 0), 1) AS embalaje,
        CASE 
            WHEN (stock_maximo - stock_actual) < 0 THEN 0
            ELSE (stock_maximo - stock_actual)
        END AS sugerido_base,
        CASE 
            WHEN UPPER(LTRIM(RTRIM(nombre_almacen))) = 'MERCASUR CALDAS' 
                THEN CAST(1.30 AS DECIMAL(10,4))
            ELSE CAST(1.50 AS DECIMAL(10,4))
        END AS factor_almacen
    FROM Base
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
    embalaje                                   AS [Embalaje],
    ultimo_costo                               AS [UltimoCosto],
    tipo                                       AS [Tipo],
    clasificacion                              AS [Clasificacion],
    sugerido_base                              AS [SugeridoBase],
    factor_almacen                             AS [Factor],
    CASE 
        WHEN sugerido_base <= 0 THEN 0
        WHEN embalaje <= 0 THEN CEILING(CAST(sugerido_base AS DECIMAL(18,4)) * factor_almacen)
        ELSE CEILING( (CAST(sugerido_base AS DECIMAL(18,4)) * factor_almacen) 
                      / CAST(embalaje AS DECIMAL(18,4)) ) * embalaje
    END                                         AS [Sugerido],
    CASE 
        WHEN sugerido_base <= 0 THEN 0
        WHEN embalaje <= 0 THEN CEILING(CAST(sugerido_base AS DECIMAL(18,4)) * factor_almacen)
        ELSE CEILING( (CAST(sugerido_base AS DECIMAL(18,4)) * factor_almacen) 
                      / CAST(embalaje AS DECIMAL(18,4)) ) * embalaje
    END  / NULLIF(embalaje, 0)				AS [Cajas],
    CASE 
        WHEN sugerido_base <= 0 THEN 0
        WHEN embalaje <= 0 THEN CEILING(CAST(sugerido_base AS DECIMAL(18,4)) * factor_almacen) * ultimo_costo
        ELSE CEILING( (CAST(sugerido_base AS DECIMAL(18,4)) * factor_almacen) 
                      / CAST(embalaje AS DECIMAL(18,4)) ) * embalaje * ultimo_costo
    END                                         AS [CostoLinea],
    ultimodescuento AS [UltimoDescuentoPedido],
    CodProveedor as [CodProveedor],
    iva as [IVA]
FROM Calculos
WHERE sugerido_base > 0
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

    # ------------------------ Evitar duplicados por lote ------------------------
    existentes = set(
        SugeridoLinea.objects.filter(lote=proceso)
        .values_list("cod_almacen", "codigo_articulo")
    )

    registros = []
    insertados = 0
    omitidos = 0

    for _, row in df.iterrows():
        cod_alm = _safe_str(row.get("CODALMACEN"))
        cod_art = _safe_str(row.get("Código"))

        if (cod_alm, cod_art) in existentes:
            omitidos += 1
            continue
        existentes.add((cod_alm, cod_art))

        prov_name = _safe_str(row.get("Proveedor"))
        marca_name = _safe_str(row.get("Marca"))

        proveedor_id = prov_map.get(prov_name) or default_prov_id
        marca_id = marca_map.get(marca_name) if marca_name else None

        registros.append(
            SugeridoLinea(
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
                descripcion=_safe_str(row.get("Descripción")) or None,
                stock_actual=_safe_int(row.get("StockActual")),
                stock_minimo=_safe_int(row.get("StockMinimo")),
                stock_maximo=_safe_int(row.get("StockMaximo")),
                uds_compra_base=_safe_int(row.get("UdsCompraBase"), 1),
                uds_compra_mult=_safe_int(row.get("UdsCompraMult"), 1),
                embalaje=_safe_int(row.get("Embalaje"), 1),
                ultimo_costo=_safe_float(row.get("UltimoCosto")),
                tipo=_safe_str(row.get("Tipo")) or None,
                clasificacion=_safe_str(row.get("Clasificacion")) or None,
                sugerido_base=_safe_int(row.get("SugeridoBase")),
                factor_almacen=_safe_float(row.get("Factor"), 1.0),
                sugerido_calculado=_safe_int(row.get("Sugerido")),
                cajas_calculadas=_safe_float(row.get("Cajas")),
                costo_linea=_safe_float(row.get("CostoLinea")),
                descuento_prov_pct=_safe_float(row.get("UltimoDescuentoPedido")),
                cod_proveedor=_safe_str(row.get("CodProveedor")) or None,
                IVA=_safe_float(row.get("IVA"), 0.0),
            )
        )
        insertados += 1

    with transaction.atomic():
        if registros:
            SugeridoLinea.objects.bulk_create(registros, batch_size=1000)
        # Evitar poner estado 'PROCESADO' en SugeridoLote desde este servicio
        # ...existing code...
    # ...existing code...

    return (
        f"Proceso #{proceso.pk} -> líneas nuevas: {insertados}, "
        f"omitidas (duplicadas en lote): {omitidos}."
    )