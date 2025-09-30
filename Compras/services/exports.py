# Compras/services/exports.py
from decimal import Decimal
import datetime
from io import BytesIO
from typing import Iterable
import datetime
from django.utils import timezone
from django.db.models import Model, QuerySet
from openpyxl import Workbook

def _excel_datetime(dt: datetime.datetime) -> datetime.datetime:
    """Convierte un datetime aware a naive (en la zona local del servidor o UTC)."""
    if timezone.is_aware(dt):
        # Opción A: llevarlo a hora local del servidor y volverlo naive
        dt = timezone.localtime(dt)
        return dt.replace(tzinfo=None)
        # Opción B (alternativa): usar UTC naive
        # return dt.astimezone(datetime.timezone.utc).replace(tzinfo=None)
    return dt  # ya es naive

def _excel_time(t: datetime.time) -> datetime.time:
    """Excel tampoco soporta tz en time(). Quita tzinfo si viene seteado."""
    if t.tzinfo is not None:
        return t.replace(tzinfo=None)
    return t

def _cellify(v):
    if v is None:
        return ""
    if isinstance(v, (str, int, float, bool, Decimal)):
        return v
    if isinstance(v, datetime.datetime):
        return _excel_datetime(v)
    if isinstance(v, datetime.date) and not isinstance(v, datetime.datetime):
        return v  # los date() puros están bien
    if isinstance(v, datetime.time):
        return _excel_time(v)
    # … (resto igual que ya te pasé) …
    from django.db.models import Model, QuerySet
    if isinstance(v, Model):
        return str(v)
    if isinstance(v, QuerySet):
        return ", ".join(map(str, v))
    if isinstance(v, (list, tuple, set)):
        return ", ".join(map(_cellify, v))
    return str(v)



# Cabeceras y mapeo de campos → cómo extraer valor de cada SugeridoLinea
HEADERS = [
    "Proveedor", "Marca", "Almacén", "Código", "Referencia" ,"Descripción",
    "Departamento", "Sección", "Familia", "Subfamilia", "Tipo",
    "Clasificación",
    "Stock actual", "Stock mínimo", "Stock máximo", "Lead time (días)", "Stock seguridad",
    "Uds compra base", "Uds compra mult", "Embalaje",
    "Último costo",
    "Sugerido base", "Factor almacén", "Sugerido calculado", "Cajas calculadas",
    "Costo línea",
    "Sugerido interno", "Comentario interno",
    "Continuidad activo", "Nuevo sugerido prov", "Desc. prov %", "Desc. prov % 2", "Desc. prov % 3",
    "Nuevo nombre prov", "Observaciones prov",
    "Estado línea",
    "Creado", "Actualizado",
    "Vendedor",
]

def _row_from_linea(ln) -> list:
    """Extrae una fila plana a partir de una instancia de SugeridoLinea."""
    return [
        _cellify(getattr(ln, "proveedor", "")),
        _cellify(getattr(ln, "marca", "")),
        _cellify(f"{getattr(ln, 'cod_almacen', '')}-{getattr(ln, 'nombre_almacen', '')}"),
        _cellify(getattr(ln, "codigo_articulo", "")),
        _cellify(getattr(ln, "referencia", "")),
        _cellify(getattr(ln, "descripcion", "")),
        _cellify(getattr(ln, "departamento", "")),
        _cellify(getattr(ln, "seccion", "")),
        _cellify(getattr(ln, "familia", "")),
        _cellify(getattr(ln, "subfamilia", "")),
        _cellify(getattr(ln, "tipo", "")),
        _cellify(getattr(ln, "clasificacion", "")),
        _cellify(getattr(ln, "stock_actual", 0)),
        _cellify(getattr(ln, "stock_minimo", 0)),
        _cellify(getattr(ln, "stock_maximo", 0)),
        _cellify(getattr(ln, "lead_time_dias", 0)),
        _cellify(getattr(ln, "stock_seguridad", 0)),
        _cellify(getattr(ln, "uds_compra_base", 1)),
        _cellify(getattr(ln, "uds_compra_mult", 1)),
        _cellify(getattr(ln, "embalaje", 1)),
        _cellify(getattr(ln, "ultimo_costo", 0)),
        _cellify(getattr(ln, "sugerido_base", 0)),
        _cellify(getattr(ln, "factor_almacen", 1)),
        _cellify(getattr(ln, "sugerido_calculado", 0)),
        _cellify(getattr(ln, "cajas_calculadas", 0)),
        _cellify(getattr(ln, "costo_linea", 0)),
        _cellify(getattr(ln, "sugerido_interno", 0)),
        _cellify(getattr(ln, "comentario_interno", "")),
        _cellify(getattr(ln, "continuidad_activo", True)),
        _cellify(getattr(ln, "nuevo_sugerido_prov", 0)),
        _cellify(getattr(ln, "descuento_prov_pct", 0)),
        _cellify(getattr(ln, "descuento_prov_pct_2", 0)),
        _cellify(getattr(ln, "descuento_prov_pct_3", 0)),
        _cellify(getattr(ln, "nuevo_nombre_prov", "")),
        _cellify(getattr(ln, "observaciones_prov", "")),
        _cellify(getattr(ln, "estado_linea", "")),
        _cellify(ln.creado.date() if ln.creado else None),
        _cellify(ln.actualizado.date() if ln.actualizado else None),
        _cellify(getattr(ln, "vendedor", "")),
    ]


def export_lines_to_xlsx(lineas: Iterable, filename="sugerido.xlsx"):
    """
    Acepta un QuerySet de SugeridoLinea (o lista iterable de instancias) y
    devuelve (bytes_xlsx, filename).
    """
    wb = Workbook()
    ws = wb.active
    ws.title = "Líneas Sugerido"

    # Cabeceras
    ws.append(HEADERS)

    # Si es QuerySet, optimiza FKs
    if isinstance(lineas, QuerySet):
        lineas = lineas.select_related("proveedor", "marca", "vendedor")

    for ln in lineas:
        ws.append(_row_from_linea(ln))

    # Auto ancho simple
    for col in ws.columns:
        max_len = max((len(str(c.value)) if c.value is not None else 0) for c in col)
        ws.column_dimensions[col[0].column_letter].width = min(max(10, max_len + 2), 60)

    bio = BytesIO()
    wb.save(bio)
    bio.seek(0)
    return bio.getvalue(), filename
