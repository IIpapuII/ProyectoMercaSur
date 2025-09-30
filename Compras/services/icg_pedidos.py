# Compras/services/icg_pedidos.py
from decimal import Decimal, ROUND_HALF_UP
from math import floor, ceil
from datetime import datetime
from django.utils import timezone
from Compras.models import SugeridoLote, SugeridoLinea
from appMercaSur.conect import conectar_sql_server


DEFAULT_NUMSERIE = "13CP"
DEFAULT_SUBSERIE_N = "B"
DEFAULT_TIPODOC = 2
DEFAULT_IDESTADO = -1
DEFAULT_CODMONEDA = 1
DEFAULT_FACTORMONEDA = Decimal("1.0")
DEFAULT_IVAINCLUIDO = "F"
DEFAULT_PORTESPAG = "T"
DEFAULT_TODORECIBIDO = "F"
DEFAULT_NORECIBIDO = "T"
DEFAULT_FROMPEDVENTACENTRAL = "F"
DEFAULT_SERIEALBARAN = ""
DEFAULT_NUMEROALBARAN = -1
DEFAULT_NALBARAN = "B"
DEFAULT_TRANSPORTE = 0
DEFAULT_NBULTOS = 0
DEFAULT_REGIMFACT = "3"
DEFAULT_ENVIOPOR = ""
DEFAULT_CONTACTO = -1
DEFAULT_CODEMPLEADO = -1
DEFAULT_NUMIMPRESIONES = 0


def _round2(x: Decimal) -> Decimal:
    return (x or Decimal("0")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

def _fmt_dtotexto(dto_pct: Decimal) -> str:
    if not dto_pct or dto_pct == 0:
        return ""
    return f"-{dto_pct}%"

def _now_naive() -> datetime:
    return timezone.localtime().replace(tzinfo=None)

def _date_zero_today() -> datetime:
    today = timezone.localdate()
    return datetime(today.year, today.month, today.day, 0, 0, 0)

def _hora_excel_naive() -> datetime:
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
    q = lin.sugerido_interno or Decimal("0")
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
    return Decimal(str((ceil(x / pack)) * pack))

def _precio_y_descuento(lin: SugeridoLinea) -> tuple[Decimal, Decimal]:
    d1 = (lin.descuento_prov_pct or Decimal("0")) / Decimal("100")
    d2 = (lin.descuento_prov_pct_2 or Decimal("0")) / Decimal("100")
    d3 = (lin.descuento_prov_pct_3 or Decimal("0")) / Decimal("100")
    comp = (Decimal("1") - (Decimal("1") - d1) * (Decimal("1") - d2) * (Decimal("1") - d3)) * Decimal("100")
    precio_base = lin.ultimo_costo or Decimal("0")
    return (_round2(precio_base), comp.quantize(Decimal("0.00000000000001")))

def _impuestos_de_linea(lin: SugeridoLinea) -> tuple[int, Decimal]:
    iva_val = getattr(lin, "iva", None)
    if iva_val is None:
        iva_val = getattr(lin, "IVA", 0)
    iva_pct = Decimal(str(iva_val or 0))
    tipo = 4 if iva_pct == 0 else 1
    return (tipo, iva_pct)

def _get_campo_clasificacion_por_almacen(almacen: str | None) -> str | None:
    a = (almacen or "").upper().strip()
    return {
        "MERCASUR CALDAS":    "CLASIFICACION",
        "MERCASUR CENTRO":    "CLASIFICACION2",
        "MERCASUR CABECERA":  "CLASIFICACION3",
        "MERCASUR SOTOMAYOR": "CLASIFICACION5",
    }.get(a)

def _actualizar_clasificacion_si_activo(cursor, lin: SugeridoLinea):
    
    if getattr(lin, "continuidad_activo", None):
        return
    nombre_almacen = getattr(lin, "nombre_almacen", None) or getattr(lin, "almacen", None)
    campo = _get_campo_clasificacion_por_almacen(nombre_almacen)
    if not campo:
        return
    codart = int(lin.codigo_articulo) if str(lin.codigo_articulo).isdigit() else lin.codigo_articulo
    print(f"Actualizando clasificación en ICG: artículo {codart}, campo {campo} = 'I'")
    cursor.execute(f"UPDATE ARTICULOSCAMPOSLIBRES SET CLASIFICACION = 'I', CLASIFICACION2 = 'I', CLASIFICACION3 =  'I', CLASIFICACION5= 'I' WHERE CODARTICULO = ?", ( codart))

def _actualizar_clasificacion_Almacen(cursor, lin: SugeridoLinea):
    nueva = getattr(lin, "clasificacion", None)
    original = getattr(lin, "clasificacion_original", None)
    if nueva is None or original is None or str(nueva) == str(original):
        return
    nombre_almacen = getattr(lin, "nombre_almacen", None) or getattr(lin, "almacen", None)
    campo = _get_campo_clasificacion_por_almacen(nombre_almacen)
    if not campo:
        return
    codart = int(lin.codigo_articulo) if str(lin.codigo_articulo).isdigit() else lin.codigo_articulo
    cursor.execute(f"UPDATE ARTICULOSCAMPOSLIBRES SET {campo} = ? WHERE CODARTICULO = ?", ('I', codart))

def crear_pedido_compra_desde_lote(
    lote_id: int,
    numserie: str = DEFAULT_NUMSERIE,
    subserie_n: str = DEFAULT_SUBSERIE_N,
    politica_cantidades: str = "prefer_interno",
    ajuste_multiplo: str = "up",
):
    lote = SugeridoLote.objects.select_related("proveedor").get(pk=lote_id)
    if not lote.proveedor:
        raise ValueError("El lote no tiene proveedor asignado.")

    codprove = getattr(lote.proveedor, "cod_icg", None) or getattr(lote.proveedor, "codigo", None)
    if codprove in (None, "", 0):
        raise ValueError("El proveedor no tiene código ICG (campo 'cod_icg' o 'codigo').")

    lineas = list(
        lote.lineas.select_related("proveedor", "marca")
        .filter(sugerido_interno__gt=0)
        .all()
    )
    if not lineas:
        raise ValueError("El lote no tiene líneas con sugerido interno > 0.")

    grupos = {}
    for lin in lineas:
        grupos.setdefault(lin.cod_almacen, []).append(lin)

    pedidos_creados = []
    lineas_ordenadas_ids = []

    conexion = conectar_sql_server()
    cursor = conexion.cursor()

    try:
        conexion.autocommit = False

        dt_now = _now_naive()
        date_zero = _date_zero_today()
        hora_excel = _hora_excel_naive()

        for cod_almacen, lista in grupos.items():
            lista_validas = [lin for lin in lista if _elegir_cantidad(lin, politica_cantidades, ajuste_multiplo) > 0]
            if not lista_validas:
                continue

            numpedido = _next_numpedido(cursor, numserie)
            supedido = f"-{numserie}-{numpedido}"

            tot_bruto = Decimal("0")
            tot_impuestos = Decimal("0")
            tot_neto = Decimal("0")

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

            numlinea = 0
            for lin in lista_validas:
                q = _elegir_cantidad(lin, politica_cantidades, ajuste_multiplo)
                if q <= 0:
                    continue

                precio_base, dto_pct = _precio_y_descuento(lin)
                tipoimp, iva_pct = _impuestos_de_linea(lin)

                total_linea_sin_iva = _round2(precio_base * (Decimal("1") - (dto_pct / Decimal("100"))) * q)
                iva_linea = _round2(total_linea_sin_iva * (iva_pct / Decimal("100"))) if iva_pct else Decimal("0")
                total_linea = total_linea_sin_iva + iva_linea

                tot_bruto += total_linea_sin_iva
                tot_impuestos += iva_linea
                tot_neto += total_linea

                numlinea += 1

                codart = int(lin.codigo_articulo) if str(lin.codigo_articulo).isdigit() else lin.codigo_articulo

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

                _actualizar_clasificacion_si_activo(cursor, lin)
                _actualizar_clasificacion_Almacen(cursor, lin)
                lineas_ordenadas_ids.append(lin.id)

            cursor.execute("""
                UPDATE PEDCOMPRACAB
                SET TOTBRUTO = ?, TOTIMPUESTOS = ?, TOTNETO = ?
                WHERE NUMSERIE = ? AND NUMPEDIDO = ? AND N = ?
            """, (float(_round2(tot_bruto)), float(_round2(tot_impuestos)), float(_round2(tot_neto)),
                  numserie, numpedido, subserie_n))

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

    if lineas_ordenadas_ids:
        SugeridoLinea.objects.filter(id__in=lineas_ordenadas_ids)\
            .update(estado_linea=SugeridoLinea.EstadoLinea.ORDENADA)

    SugeridoLote.objects.filter(pk=lote_id).update(
        estado=SugeridoLote.Estado.COMPLETADO,
        pedidos_icg=pedidos_creados
    )

    return pedidos_creados
