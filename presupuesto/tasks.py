from presupuesto.models import CategoriaVenta, PresupuestoMensualCategoria
from .utils import calcular_presupuesto_diario_forecast, cargar_ventas_reales_carne, cargasr_ventas_reales_ecenarios, cargar_ventas_reales_marca_mercasur
from datetime import date, timedelta
from celery import shared_task
import calendar
from django.utils.timezone import now

@shared_task
def cargar_ventas_hoy_carne():
    hoy = date.today()
    print(hoy)
    cargar_ventas_reales_carne(hoy, hoy)

@shared_task
def cargar_ventas_hoy_ecenarios():
    hoy = date.today()
    print(hoy)
    cargasr_ventas_reales_ecenarios(hoy, hoy)
    
@shared_task
def cargar_ventas_historicas():
    """
    Tarea Celery: ejecuta cargar_ventas_reales dia a dia,
    recorriendo meses y días mediante el módulo calendar
    desde enero de 2024 hasta la fecha actual.
    """
    mes = date.today().month
    año = date.today().year
    inicio = date(año, mes, 1)
    fin = date.today()

    # Iterar años, meses y días con calendar
    for año in range(inicio.year, fin.year + 1):
        mes_inicio = inicio.month if año == inicio.year else 1
        mes_fin = fin.month if año == fin.year else 12
        for mes in range(mes_inicio, mes_fin + 1):
            _, dias_en_mes = calendar.monthrange(año, mes)
            dia_inicio = inicio.day if (año == inicio.year and mes == inicio.month) else 1
            dia_fin = fin.day if (año == fin.year and mes == fin.month) else dias_en_mes
            for dia in range(dia_inicio, dia_fin + 1):
                fecha_actual = date(año, mes, dia)
                cargar_ventas_reales_carne(fecha_actual, fecha_actual)
                cargasr_ventas_reales_ecenarios(fecha_actual, fecha_actual)
                cargar_ventas_reales_marca_mercasur(fecha_actual, fecha_actual)
    print(f"Ventas cargadas desde {inicio} hasta {fin}.")


@shared_task
def calcular_presupuesto_diario_mes_actual():
    """
    Task para calcular el presupuesto diario de todos los registros del mes actual.
    """
    exitos = 0
    errores = 0
    hoy = now().date()
    anio_actual = hoy.year
    mes_actual = hoy.month

    categoria = CategoriaVenta.objects.filter(nombre='MARCA mercasur').first()

    presupuestos = PresupuestoMensualCategoria.objects.filter(anio=anio_actual, mes=mes_actual, categoria= categoria )

    for presupuesto in presupuestos:
        try:
            resultado = calcular_presupuesto_diario_forecast(presupuesto)
            print(f"[✔] {presupuesto}: {resultado}")
            exitos += 1
        except Exception as e:
            print(f"[✖] Error en {presupuesto}: {e}")
            errores += 1

    return {
        "total": presupuestos.count(),
        "exitosos": exitos,
        "errores": errores
    }

@shared_task
def calcular_presupuesto_diario_marca_mercasur():
    """
    Task para calcular el presupuesto diario de la categoría MARCA mercasur del mes actual.
    """
    exitos = 0
    errores = 0
    
    hoy = now().date()
    anio = hoy.year
    mes = hoy.month

    categoria = CategoriaVenta.objects.filter(nombre='MARCA mercasur').first()
    
    if not categoria:
        return {
            "error": "No se encontró la categoría 'MARCA mercasur'",
            "total": 0,
            "exitosos": 0,
            "errores": 0
        }

    presupuestos = PresupuestoMensualCategoria.objects.filter(
        anio=anio, 
        mes=mes, 
        categoria=categoria
    )

    for presupuesto in presupuestos:
        try:
            resultado = calcular_presupuesto_diario_forecast(presupuesto)
            print(f"[✔] {presupuesto}: {resultado}")
            exitos += 1
        except Exception as e:
            print(f"[✖] Error en {presupuesto}: {e}")
            errores += 1

    return {
        "total": presupuestos.count(),
        "exitosos": exitos,
        "errores": errores,
        "anio": anio,
        "mes": mes
    }
