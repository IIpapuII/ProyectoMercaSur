from .utils import cargar_ventas_reales_carne, cargasr_ventas_reales_ecenarios
from datetime import date, timedelta
from celery import shared_task
import calendar

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
    inicio = date(2025, mes, 1)
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
    print(f"Ventas cargadas desde {inicio} hasta {fin}.")