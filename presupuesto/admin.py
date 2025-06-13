from django.contrib import admin, messages
from import_export.admin import ImportExportModelAdmin # Importar el mixin
from decimal import Decimal
import logging
from django.db import transaction
from django.db.models import Q, Sum
from .actions import calcular_presupuesto_diario_action
logger = logging.getLogger(__name__)


from presupuesto.utils import recalcular_presupuestos_diarios_para_periodo

# Importar modelos y recursos
from .models import VentaDiariaReal, ventapollos, Sede, CategoriaVenta, PorcentajeDiarioConfig, PresupuestoMensualCategoria, PresupuestoDiarioCategoria
from .resources import SedeResource, CategoriaVentaResource, PorcentajeDiarioConfigResource, PresupuestoMensualCategoriaResource, PresupuestoDiarioCategoriaResource, VentapollosResource, VentaDiariaRealResource

@admin.register(Sede)
class SedeAdmin(ImportExportModelAdmin): # Usar ImportExportModelAdmin
    resource_class = SedeResource       # Vincular el recurso
    list_display = ('nombre',)
    search_fields = ('nombre',)

@admin.register(CategoriaVenta)
class CategoriaVentaAdmin(ImportExportModelAdmin):
    resource_class = CategoriaVentaResource
    list_display = ('nombre',)
    search_fields = ('nombre',)

@admin.register(PorcentajeDiarioConfig)
class PorcentajeDiarioConfigAdmin(ImportExportModelAdmin):
    resource_class = PorcentajeDiarioConfigResource
    list_display = ('sede', 'categoria', 'get_dia_semana_display', 'porcentaje')
    list_filter = ('sede__nombre', 'categoria__nombre',)
    ordering = ('sede__nombre', 'categoria__nombre', 'dia_semana',)
    list_editable = ('porcentaje',)
    list_per_page = 49

    @admin.display(description='Día de la Semana', ordering='dia_semana')
    def get_dia_semana_display(self, obj):
        return obj.get_dia_semana_display()

    # Tu acción personalizada no se ve afectada
    def check_percentage_sum(self, request, queryset):
        # ... (código de tu acción) ...
        pass
    check_percentage_sum.short_description = "Verificar suma de porcentajes (100)"
    actions = [check_percentage_sum]

@admin.register(PresupuestoMensualCategoria)
class PresupuestoMensualCategoriaAdmin(ImportExportModelAdmin):
    # --- Tu configuración actual ---
    resource_class = PresupuestoMensualCategoriaResource
    list_display = ('sede', 'categoria', 'anio', 'mes', 'presupuesto_total_categoria_format')
    list_filter = ('sede__nombre', 'categoria__nombre', 'anio', 'mes')
    search_fields = ('sede__nombre', 'categoria__nombre')
    ordering = ('sede__nombre', 'anio', 'mes', 'categoria__nombre')
    list_per_page = 31
    actions = [calcular_presupuesto_diario_action]

    @admin.display(description='valor ($)', ordering='presupuesto_total_categoria')
    def presupuesto_total_categoria_format(self, obj):
        return f"${obj.presupuesto_total_categoria:,.2f}"

    # --- Lógica de recálculo y notificación ---
    @transaction.atomic
    def save_model(self, request, obj, form, change):
        sid = transaction.savepoint()
        try:
            super().save_model(request, obj, form, change)

            success, message = recalcular_presupuestos_diarios_para_periodo(
                sede_id=obj.sede_id,
                anio=obj.anio,
                mes=obj.mes
            )

            if success:
                self.message_user(request, message, level=messages.SUCCESS)
                transaction.savepoint_commit(sid)
            else:
                raise Exception(message)

        except Exception as e:
            transaction.savepoint_rollback(sid)
            logger.error(
                f"ROLLBACK: Fallo en guardado/recálculo para Sede {obj.sede_id} ({obj.mes}/{obj.anio}): {e}",
                exc_info=True
            )
            self.message_user(request, str(e), level=messages.ERROR)

@admin.register(PresupuestoDiarioCategoria)
class PresupuestoDiarioCategoriaAdmin(ImportExportModelAdmin):
    resource_class = PresupuestoDiarioCategoriaResource
    list_display = (
        'fecha', 'get_sede', 'get_categoria', 'dia_semana_nombre',
        'porcentaje_dia_especifico', 'presupuesto_calculado_format'
    )
    list_filter = (
        'presupuesto_mensual__sede__nombre',
        'presupuesto_mensual__categoria__nombre',
        'fecha'
    )
    search_fields = (
        'presupuesto_mensual__sede__nombre',
        'presupuesto_mensual__categoria__nombre',
        'fecha'
    )
    ordering = ('-fecha', 'presupuesto_mensual__sede__nombre', 'presupuesto_mensual__categoria__nombre')
    list_per_page = 30
    date_hierarchy = 'fecha'

    @admin.display(description='Sede', ordering='presupuesto_mensual__sede__nombre')
    def get_sede(self, obj):
        return obj.presupuesto_mensual.sede.nombre

    @admin.display(description='Categoría', ordering='presupuesto_mensual__categoria__nombre')
    def get_categoria(self, obj):
        return obj.presupuesto_mensual.categoria.nombre
    
    @admin.display(description='Presupuesto ($)', ordering='presupuesto_calculado')
    def presupuesto_calculado_format(self, obj):
        return f"${obj.presupuesto_calculado:,.2f}"

@admin.register(ventapollos)
class VentapollosAdmin(ImportExportModelAdmin):
    resource_class = VentapollosResource
    list_display = ('id', 'fecha', 'ubicacion', 'ValorVenta', 'create_date', 'update_date')
    list_filter = ('fecha', 'ubicacion')
    search_fields = ('fecha', 'ubicacion')
    ordering = ('-fecha',)
    date_hierarchy = 'fecha'
    list_per_page = 10

@admin.register(VentaDiariaReal)
class VentaDiariaRealAdmin(ImportExportModelAdmin):
    resource_class = VentaDiariaRealResource
    list_display = ('fecha', 'get_sede_nombre', 'get_categoria_nombre', 'venta_real_formatted')
    list_filter = ('fecha', 'sede__nombre', 'categoria__nombre')
    search_fields = ('sede__nombre', 'categoria__nombre', 'fecha')
    date_hierarchy = 'fecha'
    ordering = ('-fecha', 'sede__nombre', 'categoria__nombre')
    list_per_page = 25

    @admin.display(description='Sede', ordering='sede__nombre')
    def get_sede_nombre(self, obj):
        return obj.sede.nombre

    @admin.display(description='Categoría', ordering='categoria__nombre')
    def get_categoria_nombre(self, obj):
        return obj.categoria.nombre

    @admin.display(description='Venta Real ($)', ordering='venta_real')
    def venta_real_formatted(self, obj):
        return f"${obj.venta_real:,.2f}"