from django.contrib import admin
from django.contrib import messages
from .utils import calcular_presupuesto_diario_forecast


def calcular_presupuesto_diario_action(modeladmin, request, queryset):
    """
    Acción personalizada para calcular el presupuesto diario forecast.
    """
    exitos = 0
    errores = 0
    for presupuesto in queryset:
        try:
            print(presupuesto)
            resultado = calcular_presupuesto_diario_forecast(presupuesto)
            exitos += 1
            messages.success(request, f'Presupuesto diario calculado para {presupuesto}: {resultado}')
        except Exception as e:
            errores += 1
            messages.error(request, f'Error para {presupuesto}: {e}')
    messages.success(request, f'¡{exitos} presupuestos diarios calculados correctamente! {errores} errores.')

calcular_presupuesto_diario_action.short_description = "Calcular Presupuesto Diario Forecast"
