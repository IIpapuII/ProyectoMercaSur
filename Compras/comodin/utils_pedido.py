# Compras/services/icg_pedidos.py
from decimal import Decimal, ROUND_HALF_UP
from math import floor, ceil
from datetime import datetime, timedelta

from django.utils import timezone

from Compras.models import SugeridoLote, SugeridoLinea
from appMercaSur.conect import conectar_sql_server


def _round2(x: Decimal) -> Decimal:
    """Redondeo a 2 decimales."""
    return (x or Decimal("0")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _fmt_dtotexto(dto_pct: Decimal) -> str:
    """Formatea el texto del descuento como '-X%' o vacío si es 0."""
    if not dto_pct or dto_pct == 0:
        return ""
    return f"-{dto_pct}%"


def _now_naive() -> datetime:
    """Datetime local sin tzinfo (para SQL Server)."""
    return timezone.localtime().replace(tzinfo=None)


def _date_zero_today() -> datetime:
    """Fecha a 00:00:00 del día local."""
    today = timezone.localdate()
    return datetime(today.year, today.month, today.day, 0, 0, 0)


def _hora_excel_naive() -> datetime:
    """Hora estilo Excel (base 1899-12-30) sin tzinfo."""
    now_local = timezone.localtime()
    return datetime(1899, 12, 30, now_local.hour, now_local.minute, now_local.second)


def _next_numpedido(cursor, numserie: str) -> int:
    """Obtiene el siguiente número de pedido bloqueando la serie."""
    cursor.execute(
        """
        SELECT ISNULL(MAX(NUMPEDIDO), 0)
        FROM PEDCOMPRACAB WITH (UPDLOCK, HOLDLOCK)
        WHERE NUMSERIE = ?
        """,
        (numserie,),
    )
    row = cursor.fetchone()
    return (row[0] or 0) + 1


def _elegir_cantidad(lin: SugeridoLinea, politica: str, ajuste: str) -> Decimal:
    """
    Devuelve la cantidad ajustada a múltiplos de embalaje según la política.
    politica se mantiene por compatibilidad; la lógica usa 'ajuste' (up/down/nearest).
    """
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
    # default: "up"
    return Decimal(str((ceil(x / pack)) * pack))


def _precio_y_descuento(lin: SugeridoLinea) -> tuple[Decimal, Decimal]:
    """
    Retorna (precio_base, dto_compuesto_en_%).
    El descuento compuesto es la composición de hasta 3 descuentos porcentuales.
    """
    d1 = (lin.descuento_prov_pct or Decimal("0")) / Decimal("100")
    d2 = (lin.descuento_prov_pct_2 or Decimal("0")) / Decimal("100")
    d3 = (lin.descuento_prov_pct_3 or Decimal("0")) / Decimal("100")
    comp = (Decimal("1") - (Decimal("1") - d1) * (Decimal("1") - d2) * (Decimal("1") - d3)) * Decimal("100")
    precio_base = lin.ultimo_costo or Decimal("0")
    return (_round2(precio_base), comp.quantize(Decimal("0.00000000000001")))


def _impuestos_de_linea(cursor, lin: SugeridoLinea) -> tuple[int, Decimal]:
    """
    Obtiene (TIPOIMPUESTO, IVA%) desde ARTICULOS + IMPUESTOS.
    Si falla, usa los valores del modelo como respaldo.
    """
    codart = int(lin.codigo_articulo) if str(lin.codigo_articulo).isdigit() else lin.codigo_articulo
    try:
        cursor.execute(
            """
            SELECT A.IMPUESTOCOMPRA AS ID, I.IVA AS VALOR
            FROM ARTICULOS A
            INNER JOIN IMPUESTOS I ON I.TIPOIVA = A.IMPUESTOCOMPRA
            WHERE A.CODARTICULO = ?
            """,
            (codart,),
        )
        row = cursor.fetchone()
        if row:
            tipo_impuesto = int(row[0] or 4)  # 4 si es None
            iva_pct = Decimal(str(row[1] or 0))
            return (tipo_impuesto, iva_pct)
        return (4, Decimal("0"))
    except Exception as e:
        print(f"Error al obtener impuestos para artículo {codart}: {e}")
        iva_val = getattr(lin, "iva", None)
        if iva_val is None:
            iva_val = getattr(lin, "IVA", 0)
        iva_pct = Decimal(str(iva_val or 0))
        tipo = 4 if iva_pct == 0 else 1
        return (tipo, iva_pct)


def _obtener_cargos_articulo(cursor, codigo_articulo: str) -> dict[str, Decimal]:
    """
    Obtiene CARGO1..CARGO6 (porcentajes en maestro de ARTICULOS) y los devuelve
    solo si su código asociado en CARGOSDTOS tiene VISIBLECOMPRA = 'T'.
    Si no aplica, devuelve 0 por defecto.

    Mapeo de posiciones -> códigos en CARGOSDTOS:
      CARGO1 -> 3
      CARGO2 -> 34
      CARGO3 -> 39
      CARGO4 -> 40
      CARGO5 -> 41
      CARGO6 -> 42
    """
    resultado = {f"CARGO{i}": Decimal("0") for i in range(1, 7)}

    try:
        # 1) Leer los 6 cargos del artículo
        cursor.execute(
            """
            SELECT CARGO1, CARGO2, CARGO3, CARGO4, CARGO5, CARGO6
            FROM ARTICULOS
            WHERE CODARTICULO = ?
            """,
            (codigo_articulo,),
        )
        row = cursor.fetchone()
        if not row:
            return resultado  # no hay artículo → todo 0

        # 2) Traer visibilidad de compra por código de cargo
        cargo_code_map = {"CARGO1": 3, "CARGO2": 34, "CARGO3": 39, "CARGO4": 40, "CARGO5": 41, "CARGO6": 42}
        codigos = list(cargo_code_map.values())
        placeholders = ",".join("?" for _ in codigos)

        cursor.execute(
            f"""
            SELECT CODIGO, VISIBLECOMPRA
            FROM CARGOSDTOS
            WHERE CODIGO IN ({placeholders})
            """,
            codigos,
        )

        visibles_por_codigo: dict[int, bool] = {}
        for codigo, visiblecompra in cursor.fetchall():
            visibles_por_codigo[int(codigo)] = (str(visiblecompra).strip().upper() == "T")

        # 3) Construir dict aplicando reglas
        nombres = ["CARGO1", "CARGO2", "CARGO3", "CARGO4", "CARGO5", "CARGO6"]
        for idx, nombre in enumerate(nombres):
            valor = row[idx]
            codigo_cargo = cargo_code_map[nombre]
            visible = visibles_por_codigo.get(codigo_cargo, False)

            if visible and valor not in (None, 0, 0.0, "0", "0.0"):
                try:
                    resultado[nombre] = Decimal(str(valor))
                except Exception:
                    resultado[nombre] = Decimal("0")
            else:
                resultado[nombre] = Decimal("0")

        return resultado

    except Exception:
        return {f"CARGO{i}": Decimal("0") for i in range(1, 7)}


def _get_campo_clasificacion_por_almacen(almacen: str | None) -> str | None:
    a = (almacen or "").upper().strip()
    return {
        "MERCASUR CALDAS": "CLASIFICACION",
        "MERCASUR CENTRO": "CLASIFICACION2",
        "MERCASUR CABECERA": "CLASIFICACION3",
        "MERCASUR SOTOMAYOR": "CLASIFICACION5",
    }.get(a)


def _actualizar_clasificacion_si_activo(cursor, lin: SugeridoLinea):
    """Marca I (activo/continuidad) en todos los campos de clasificación si corresponde."""
    if getattr(lin, "continuidad_activo", None):
        return
    nombre_almacen = getattr(lin, "nombre_almacen", None) or getattr(lin, "almacen", None)
    campo = _get_campo_clasificacion_por_almacen(nombre_almacen)
    if not campo:
        return
    codart = int(lin.codigo_articulo) if str(lin.codigo_articulo).isdigit() else lin.codigo_articulo
    print(f"Actualizando clasificación en ICG: artículo {codart}, campo {campo} = 'I'")
    cursor.execute(
        "UPDATE ARTICULOSCAMPOSLIBRES "
        "SET CLASIFICACION='I', CLASIFICACION2='I', CLASIFICACION3='I', CLASIFICACION5='I' "
        "WHERE CODARTICULO = ?",
        (codart,),
    )


def _actualizar_clasificacion_Almacen(cursor, lin: SugeridoLinea):
    """Actualiza solo el campo de clasificación del almacén si cambió respecto al original."""
    nueva = getattr(lin, "clasificacion", None)
    original = getattr(lin, "clasificacion_original", None)
    if nueva is None or original is None or str(nueva) == str(original):
        return

    nombre_almacen = getattr(lin, "nombre_almacen", None) or getattr(lin, "almacen", None)
    campo = _get_campo_clasificacion_por_almacen(nombre_almacen)
    if not campo:
        return

    codart = int(lin.codigo_articulo) if str(lin.codigo_articulo).isdigit() else lin.codigo_articulo
    cursor.execute(
        f"UPDATE ARTICULOSCAMPOSLIBRES SET {campo} = ? WHERE CODARTICULO = ?",
        ("I", codart),
    )


def _obtener_descuentos_proveedor(cursor, codproveedor: int) -> list[tuple[int, Decimal]]:
    """
    Devuelve lista de (CODIGO, VALOR%) desde CARGOSDTOSPROVEEDOR para el proveedor.
    - Solo retorna filas con VALOR > 0.
    - VALOR se interpreta como porcentaje (ej: 10 para 10%).
    """
    try:
        cursor.execute(
            """
            SELECT CODIGO, VALOR
            FROM CARGOSDTOSPROVEEDOR
            WHERE CODPROVEEDOR = ?
            """,
            (int(codproveedor),),
        )
        res = []
        for codigo, valor in cursor.fetchall() or []:
            try:
                # VALOR viene como porcentaje directo (ej: 10 para 10%)
                v = Decimal(str(valor or 0)).quantize(Decimal("0.01"))
                # Asegurar que sea positivo
                v = abs(v)
            except Exception as e:
                print(f"Error convirtiendo valor de descuento: {valor}, error: {e}")
                v = Decimal("0")
            if v > 0:
                try:
                    c = int(codigo)
                except Exception:
                    c = int(str(codigo).strip())
                print(f"DEBUG: Descuento proveedor - Código: {c}, Valor%: {v}")
                res.append((c, v))
        return res
    except Exception as e:
        print(f"Error obteniendo descuentos del proveedor {codproveedor}: {e}")
        return []


def _obtener_secuencia_cargo(cursor, codigo_cargo: int) -> int:
    """
    Obtiene el campo SECUENCIA desde CARGOSDTOS para un código de cargo/descuento.
    Retorna 0 si no se encuentra.
    """
    try:
        cursor.execute(
            """
            SELECT SECUENCIA
            FROM CARGOSDTOS
            WHERE CODIGO = ?
            """,
            (int(codigo_cargo),),
        )
        row = cursor.fetchone()
        return int(row[0]) if row and row[0] is not None else 0
    except Exception:
        return 0


def _fecha_base_excel() -> datetime:
    """Fecha base de Excel (1899-12-30) para campos como FECHACARTERA."""
    return datetime(1899, 12, 30, 0, 0, 0)


def _obtener_forma_pago_proveedor(cursor, codproveedor: int) -> dict:
    """
    Obtiene CODFORMAPAGO, CODTIPOPAGO y DIAS desde FPAGOPROVEEDOR + VENCIMFPAGO.
    Retorna dict con las claves: codformapago, codtipopago, dias_vencimiento.
    Si no encuentra datos, usa valores por defecto.
    """
    try:
        cursor.execute(
            """
            SELECT DISTINCT v.CODFORMAPAGO, v.DIAS, v.CODTIPOPAGO
            FROM FPAGOPROVEEDOR f
            INNER JOIN VENCIMFPAGO v ON f.CODFORMAPAGO = v.CODFORMAPAGO
            WHERE f.CODPROVEEDOR = ?
            """,
            (int(codproveedor),),
        )
        row = cursor.fetchone()
        if row:
            return {
                "codformapago": str(row[0]) if row[0] else "14",
                "dias_vencimiento": int(row[1]) if row[1] else 30,
                "codtipopago": str(row[2]) if row[2] else "10",
            }
        return {
            "codformapago": "14",
            "dias_vencimiento": 30,
            "codtipopago": "10",
        }
    except Exception as e:
        print(f"Error al obtener forma de pago del proveedor {codproveedor}: {e}")
        return {
            "codformapago": "14",
            "dias_vencimiento": 30,
            "codtipopago": "10",
        }
