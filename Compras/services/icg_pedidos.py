# Compras/services/icg_pedidos.py
from decimal import Decimal, ROUND_HALF_UP
from math import floor, ceil
from datetime import datetime
from django.utils import timezone
from Compras.models import SugeridoLote, SugeridoLinea
from appMercaSur.conect import conectar_sql_server


# ----------------- Parámetros por defecto (ajusta a tu ICG) -----------------
DEFAULT_NUMSERIE = "13CP"       # Serie de pedido
DEFAULT_SUBSERIE_N = "B"        # Subserie N
DEFAULT_TIPODOC = 2             # Según tu ejemplo real
DEFAULT_IDESTADO = -1
DEFAULT_CODMONEDA = 1
DEFAULT_FACTORMONEDA = Decimal("1.0")
DEFAULT_IVAINCLUIDO = "F"
DEFAULT_PORTESPAG = "T"
DEFAULT_TODORECIBIDO = "F"
DEFAULT_NORECIBIDO = "T"
DEFAULT_FROMPEDVENTACENTRAL = "F"
DEFAULT_SERIEALBARAN = ""       # N''
DEFAULT_NUMEROALBARAN = -1
DEFAULT_NALBARAN = "B"
DEFAULT_TRANSPORTE = 0          # numérico
DEFAULT_NBULTOS = 0
DEFAULT_REGIMFACT = "3"         # como tu ejemplo
DEFAULT_ENVIOPOR = ""           # N''
DEFAULT_CONTACTO = -1           # numérico
DEFAULT_CODEMPLEADO = -1        # numérico
DEFAULT_NUMIMPRESIONES = 0      # si quieres 1, cámbialo


# ----------------- Utilidades -----------------
def _round2(x: Decimal) -> Decimal:
    return (x or Decimal("0")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

def _fmt_dtotexto(dto_pct: Decimal) -> str:
    """Devuelve texto tipo '-1.98967406574881%' si dto>0, vacío si no hay dto."""
    if not dto_pct or dto_pct == 0:
        return ""
    return f"-{dto_pct}%"

def _now_naive() -> datetime:
    """Fecha/hora local sin tzinfo (SQL Server no acepta tzinfo)."""
    return timezone.localtime().replace(tzinfo=None)

def _date_zero_today() -> datetime:
    """YYYY-MM-DD 00:00:00.000 (naïve) del día actual."""
    today = timezone.localdate()
    return datetime(today.year, today.month, today.day, 0, 0, 0)

def _hora_excel_naive() -> datetime:
    """
    Devuelve datetime con base 1899-12-30 HH:MM:SS.000 como objeto datetime naïve,
    replicando el patrón de ICG que compartiste.
    """
    now_local = timezone.localtime()
    return datetime(1899, 12, 30, now_local.hour, now_local.minute, now_local.second)

def _next_numpedido(cursor, numserie: str) -> int:
    cursor.execute("""
        SELECT ISNULL(MAX(NUMPEDIDO), 0)
        FROM PEDCOMPRACAB WITH (UPDLOCK, HOLDLOCK)
        WHERE NUMSERIE = ?
    """, (numserie,))
    row = cursor.fetchone()
    return (row[0] or 0) + 1

def _elegir_cantidad(lin: SugeridoLinea, politica: str, ajuste: str) -> Decimal:
    """
    politica: 'prefer_proveedor'|'prefer_interno'|'solo_calculado'
    ajuste: 'up'|'down'|'nearest'
    """
    if politica == "prefer_proveedor":
        if lin.estado_linea == SugeridoLinea.EstadoLinea.APROBADA and lin.nuevo_sugerido_prov > 0:
            q = lin.nuevo_sugerido_prov
        elif lin.sugerido_interno and lin.sugerido_interno > 0:
            q = lin.sugerido_interno
        else:
            q = lin.sugerido_base or Decimal("0")
    elif politica == "prefer_interno":
        if lin.sugerido_interno and lin.sugerido_interno > 0:
            q = lin.sugerido_interno
        elif lin.estado_linea == SugeridoLinea.EstadoLinea.APROBADA and lin.nuevo_sugerido_prov > 0:
            q = lin.nuevo_sugerido_prov
        else:
            q = lin.sugerido_base or Decimal("0")
    else:
        q = lin.sugerido_base or Decimal("0")

    if q <= 0:
        return Decimal("0")

    pack = max(int(lin.embalaje or 1), 1)
    if pack <= 1:
        return q

    x = Decimal(str(q))
    if ajuste == "down":
        return Decimal(str((floor(x / pack)) * pack))
    if ajuste == "nearest":
        d = Decimal(str((floor(x / pack)) * pack))
        u = Decimal(str((ceil(x / pack)) * pack))
        return u if (x - d) >= (u - x) else d
    return Decimal(str((ceil(x / pack)) * pack))  # up

def _precio_y_descuento(lin: SugeridoLinea) -> tuple[Decimal, Decimal]:
    """
    PRECIO: unitario base antes de dto (ej. 7118.0).
    DTO: porcentaje único equivalente (si tienes 3 descuentos, se combinan).
    """
    d1 = (lin.descuento_prov_pct or Decimal("0")) / Decimal("100")
    d2 = (lin.descuento_prov_pct_2 or Decimal("0")) / Decimal("100")
    d3 = (lin.descuento_prov_pct_3 or Decimal("0")) / Decimal("100")
    comp = (Decimal("1") - (Decimal("1") - d1) * (Decimal("1") - d2) * (Decimal("1") - d3)) * Decimal("100")
    precio_base = lin.ultimo_costo or Decimal("0")
    return (_round2(precio_base), comp.quantize(Decimal("0.00000000000001")))

def _impuestos_de_linea(lin: SugeridoLinea) -> tuple[int, Decimal]:
    """
    Devuelve (TIPOIMPUESTO, IVA%).
    Ajusta a tu codificación real. Por defecto:
    - IVA 0% => TIPOIMPUESTO = 4
    - IVA >0 => TIPOIMPUESTO = 1
    """
    iva_val = getattr(lin, "iva", None)
    if iva_val is None:
        iva_val = getattr(lin, "IVA", 0)
    iva_pct = Decimal(str(iva_val or 0))
    tipo = 4 if iva_pct == 0 else 1
    return (tipo, iva_pct)


# ----------------- Servicio principal -----------------
def crear_pedido_compra_desde_lote(
    lote_id: int,
    numserie: str = DEFAULT_NUMSERIE,
    subserie_n: str = DEFAULT_SUBSERIE_N,
    politica_cantidades: str = "prefer_interno",  # 'prefer_proveedor'|'prefer_interno'|'solo_calculado'
    ajuste_multiplo: str = "up",                  # 'up'|'down'|'nearest'
):
    """
    Crea 1..N pedidos de compra (PEDCOMPRACAB + PEDCOMPRALIN) desde un SugeridoLote,
    agrupando por CODALMACEN. Devuelve la lista de pedidos creados:
      [{'cod_almacen': '50', 'numserie': '13CP', 'numpedido': 256035, 'subserie': 'B'}, ...]
    Además, escribe el resultado dentro del SugeridoLote en el campo JSON 'pedidos_icg'.
    """
    lote = SugeridoLote.objects.select_related("proveedor").get(pk=lote_id)
    if not lote.proveedor:
        raise ValueError("El lote no tiene proveedor asignado.")

    # CODPROVEEDOR ICG
    codprove = getattr(lote.proveedor, "cod_icg", None) or getattr(lote.proveedor, "codigo", None)
    if codprove in (None, "", 0):
        raise ValueError("El proveedor no tiene código ICG (campo 'cod_icg' o 'codigo').")

    # Agrupar líneas por almacén
    lineas = list(lote.lineas.select_related("proveedor", "marca").all())
    if not lineas:
        raise ValueError("El lote no tiene líneas.")

    grupos = {}
    for lin in lineas:
        grupos.setdefault(lin.cod_almacen, []).append(lin)

    pedidos_creados = []
    lineas_ordenadas_ids = []

    # --- Conexión usando tu utilitario ---
    conexion = conectar_sql_server()
    cursor = conexion.cursor()

    try:
        conexion.autocommit = False

        # Fechas/horas como objetos datetime NAÏVE (evita 22007)
        dt_now = _now_naive()            # FECHAMODIFICADO / FECHACREACION
        date_zero = _date_zero_today()   # FECHAPEDIDO / FECHAENTREGA
        hora_excel = _hora_excel_naive() # HORA (base 1899-12-30)

        for cod_almacen, lista in grupos.items():
            # Numeración por cada pedido (por almacén)
            numpedido = _next_numpedido(cursor, numserie)
            supedido = f"-{numserie}-{numpedido}"

            # Totales por pedido
            tot_bruto = Decimal("0")
            tot_impuestos = Decimal("0")
            tot_neto = Decimal("0")

            # ---------- Encabezado del pedido (por almacén) ----------
            cursor.execute("""
                INSERT INTO PEDCOMPRACAB (
                    NUMSERIE, NUMPEDIDO, N, CODPROVEEDOR, SERIEALBARAN, NUMEROALBARAN, NALBARAN,
                    FECHAPEDIDO, FECHAENTREGA, ENVIOPOR, TOTBRUTO, DTOPP, TOTDTOPP, DTOCOMERCIAL, TOTDTOCOMERCIAL,
                    TOTIMPUESTOS, TOTNETO, CODMONEDA, FACTORMONEDA, PORTESPAG, SUPEDIDO, IVAINCLUIDO, TODORECIBIDO,
                    TIPODOC, IDESTADO, FECHAMODIFICADO, HORA, TRANSPORTE, NBULTOS, TOTALCARGOSDTOS, NORECIBIDO,
                    CODEMPLEADO, CONTACTO, FROMPEDVENTACENTRAL, FECHACREACION, NUMIMPRESIONES, REGIMFACT
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (
                numserie, numpedido, subserie_n, int(codprove),
                DEFAULT_SERIEALBARAN, DEFAULT_NUMEROALBARAN, DEFAULT_NALBARAN,
                date_zero, date_zero, DEFAULT_ENVIOPOR,
                0.0, 0.0, 0.0, 0.0, 0.0,
                0.0, 0.0,
                DEFAULT_CODMONEDA, float(DEFAULT_FACTORMONEDA),
                DEFAULT_PORTESPAG, supedido, DEFAULT_IVAINCLUIDO, DEFAULT_TODORECIBIDO,
                DEFAULT_TIPODOC, DEFAULT_IDESTADO, dt_now, hora_excel, DEFAULT_TRANSPORTE, DEFAULT_NBULTOS, 0.0, DEFAULT_NORECIBIDO,
                DEFAULT_CODEMPLEADO, DEFAULT_CONTACTO, DEFAULT_FROMPEDVENTACENTRAL, dt_now, DEFAULT_NUMIMPRESIONES, DEFAULT_REGIMFACT
            ))

            # ---------- Líneas de ese pedido ----------
            numlinea = 0
            for lin in lista:
                q = _elegir_cantidad(lin, politica_cantidades, ajuste_multiplo)
                if q <= 0:
                    continue

                precio_base, dto_pct = _precio_y_descuento(lin)
                tipoimp, iva_pct = _impuestos_de_linea(lin)

                # Total sin IVA y con IVA (IVA separado en columnas)
                total_linea_sin_iva = _round2(precio_base * (Decimal("1") - (dto_pct / Decimal("100"))) * q)
                iva_linea = _round2(total_linea_sin_iva * (iva_pct / Decimal("100"))) if iva_pct else Decimal("0")
                total_linea = total_linea_sin_iva + iva_linea

                tot_bruto += total_linea_sin_iva
                tot_impuestos += iva_linea
                tot_neto += total_linea

                numlinea += 1

                codart = int(lin.codigo_articulo) if str(lin.codigo_articulo).isdigit() else lin.codigo_articulo

                # 43 columnas => 43 placeholders
                cursor.execute("""
                    INSERT INTO PEDCOMPRALIN (
                        NUMSERIE, NUMPEDIDO, N, NUMLINEA, CODARTICULO, REFERENCIA, TALLA, COLOR, DESCRIPCION,
                        UNID1, UNID2, UNID3, UNID4, UNIDADESTOTAL, UNIDADESREC, UNIDADESPEN,
                        PRECIO, DTO, TIPOIMPUESTO, IVA, REQ, TOTALLINEA, CODALMACEN, DEPOSITO, PRECIOVENTA,
                        NUMKG, SUPEDIDO, CODCLIENTE, CARGO1, CARGO2, DTOTEXTO, ESOFERTA, FECHAENTREGA,
                        CODENVIO, UDMEDIDA2, LINEAOCULTA, CODFORMATO, CARGO3, CARGO4, CARGO5, CARGO6,
                        IMPORTEMASCARGOS, IMPORTEIVAMASCARGOS
                    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """, (
                    numserie, numpedido, subserie_n, numlinea,
                    codart, (lin.referencia or ""), ".", ".", (lin.descripcion or "")[:250],
                    float(q), 1.0, 1.0, 1.0, float(q), 0.0, float(q),
                    float(precio_base), float(dto_pct), int(tipoimp), float(iva_pct), 0.0, float(total_linea),
                    lin.cod_almacen, "F", 0.0,
                    0.0, f"-{numserie}-{numpedido}", -1, 0.0, 0.0, _fmt_dtotexto(dto_pct), "F", date_zero,
                    -1, 0.0, "F", 0, 0.0, 0.0, 0.0, 0.0,
                    0.0, 0.0
                ))

                lineas_ordenadas_ids.append(lin.id)

            # ---------- Totales del encabezado de ese pedido ----------
            cursor.execute("""
                UPDATE PEDCOMPRACAB
                SET TOTBRUTO = ?, TOTIMPUESTOS = ?, TOTNETO = ?
                WHERE NUMSERIE = ? AND NUMPEDIDO = ? AND N = ?
            """, (float(_round2(tot_bruto)), float(_round2(tot_impuestos)), float(_round2(tot_neto)),
                  numserie, numpedido, subserie_n))

            # Registrar pedido creado por almacén (para devolver/guardar)
            pedidos_creados.append({
                "cod_almacen": str(cod_almacen),
                "numserie": numserie,
                "numpedido": int(numpedido),
                "subserie": subserie_n,
                "supedido": f"-{numserie}-{numpedido}",
                "totbruto": float(_round2(tot_bruto)),
                "totimpuestos": float(_round2(tot_impuestos)),
                "totneto": float(_round2(tot_neto)),
            })

        # Commit de todos los pedidos (uno por almacén)
        conexion.commit()

    except Exception:
        conexion.rollback()
        raise
    finally:
        try:
            cursor.close()
        except Exception:
            pass
        try:
            conexion.close()
        except Exception:
            pass

    # ---------------- Post: actualizar estados en Django ----------------
    if lineas_ordenadas_ids:
        SugeridoLinea.objects.filter(id__in=lineas_ordenadas_ids)\
            .update(estado_linea=SugeridoLinea.EstadoLinea.ORDENADA)

    # Guardar resumen de pedidos en el lote SIEMPRE en 'pedidos_icg' (JSONField)
    SugeridoLote.objects.filter(pk=lote_id).update(
        estado=SugeridoLote.Estado.COMPLETADO,
        pedidos_icg=pedidos_creados
    )

    return pedidos_creados

