# apps/Compras/services/kpi_proveedores.py
from decimal import Decimal
from django.db.models import Sum, Value, DecimalField, Q
from django.db.models.functions import Coalesce
from django.utils import timezone
import datetime

from Compras.models import Proveedor


def calcular_cumplimiento_presupuesto(proveedor_id: int, ref_date: datetime.date | None = None) -> Decimal:
    """
    Devuelve únicamente el porcentaje de cumplimiento del presupuesto mensual
    de un proveedor en el mes indicado (por defecto, mes actual).
    """
    proveedor = Proveedor.objects.get(pk=proveedor_id)

    # Delimitar mes
    today = timezone.localdate()
    ref_date = ref_date or today
    start = ref_date.replace(day=1)
    if start.month == 12:
        next_month = start.replace(year=start.year + 1, month=1, day=1)
    else:
        next_month = start.replace(month=start.month + 1, day=1)

    dt_start = timezone.make_aware(datetime.datetime.combine(start, datetime.time.min))
    dt_end = timezone.make_aware(datetime.datetime.combine(next_month, datetime.time.min))

    # Total sugerido del mes
    total_sugerido_mes = proveedor.lineas_sugerido.filter(
        lote__fecha_extraccion__gte=dt_start,
        lote__fecha_extraccion__lt=dt_end,
    ).aggregate(
        total=Coalesce(Sum("costo_linea"), Value(Decimal("0.00")), output_field=DecimalField())
    )["total"] or Decimal("0.00")

    presupuesto = proveedor.presupuesto_mensual or Decimal("0.00")

    if presupuesto > 0:
        cumplimiento_pct = (total_sugerido_mes / presupuesto) * Decimal("100")
    else:
        cumplimiento_pct = Decimal("0")

    # Redondear a 2 decimales
    print(cumplimiento_pct)
    return cumplimiento_pct.quantize(Decimal("0.01"))
