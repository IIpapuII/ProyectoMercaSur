# En tu_app/resources.py

from import_export import resources, fields, widgets
from import_export.formats.base_formats import XLS, XLSX
import logging
logger = logging.getLogger(__name__)
from .utils import recalcular_presupuestos_diarios_para_periodo
from django.db import transaction
from .models import (
    Sede, CategoriaVenta, PorcentajeDiarioConfig,
    PresupuestoMensualCategoria, PresupuestoDiarioCategoria,
    ventapollos, VentaDiariaReal
)

class SedeResource(resources.ModelResource):
    class Meta:
        model = Sede
        fields = ('id', 'nombre',)
        import_id_fields = ['nombre'] 
        skip_unchanged = True
        report_skipped = True
        formats = [XLS, XLSX]

class CategoriaVentaResource(resources.ModelResource):
    class Meta:
        model = CategoriaVenta
        fields = ('id', 'nombre',)
        import_id_fields = ['nombre'] 
        skip_unchanged = True
        report_skipped = True
        formats = [XLS, XLSX]

class PorcentajeDiarioConfigResource(resources.ModelResource):
    sede = fields.Field(
        column_name='sede',
        attribute='sede',
        widget=widgets.ForeignKeyWidget(Sede, field='nombre')
    )
    categoria = fields.Field(
        column_name='categoria',
        attribute='categoria',
        widget=widgets.ForeignKeyWidget(CategoriaVenta, field='nombre')
    )

    class Meta:
        model = PorcentajeDiarioConfig
        fields = ('id', 'sede', 'categoria', 'dia_semana', 'mes' 'porcentaje')
        import_id_fields = ('sede','categoria', 'dia_semana','mes')
        skip_unchanged = True
        report_skipped = True
        formats = [XLS, XLSX]

class PresupuestoMensualCategoriaResource(resources.ModelResource):
    sede = fields.Field(column_name='sede', attribute='sede',
                        widget=widgets.ForeignKeyWidget(Sede, field='nombre'))
    categoria = fields.Field(column_name='categoria', attribute='categoria',
                             widget=widgets.ForeignKeyWidget(CategoriaVenta, field='nombre'))

    # Recolecta combinaciones únicas
    combinaciones_recalculo = set()

    def before_import_row(self, row, **kwargs):
        self.combinaciones_recalculo.add((row['sede'], row['anio'], row['mes']))

    def after_import(self, dataset, result, using_transactions, dry_run, **kwargs):
        for sede_nombre, anio, mes in self.combinaciones_recalculo:
            try:
                sede = Sede.objects.get(nombre=sede_nombre)
                success, message = recalcular_presupuestos_diarios_para_periodo(
                    sede_id=sede.id,
                    anio=anio,
                    mes=mes
                )
                if not success:
                    raise Exception(message)
            except Exception as e:
                logger.error(
                    f"[ImportError] Error al recalcular para Sede={sede_nombre}, Año={anio}, Mes={mes}: {e}",
                    exc_info=True
                )

    class Meta:
        model = PresupuestoMensualCategoria
        fields = ('id', 'sede', 'categoria', 'anio', 'mes', 'presupuesto_total_categoria')
        import_id_fields = ('sede', 'categoria', 'anio', 'mes')
        skip_unchanged = True
        report_skipped = True
        formats = [XLS, XLSX]
        
class PresupuestoDiarioCategoriaResource(resources.ModelResource):
    class Meta:
        model = PresupuestoDiarioCategoria
        fields = ('id', 'presupuesto_mensual', 'fecha', 'dia_semana_nombre', 'porcentaje_dia_especifico', 'presupuesto_calculado')
        import_id_fields = ('presupuesto_mensual', 'fecha')
        skip_unchanged = True
        report_skipped = True
        formats = [XLS, XLSX]

class VentapollosResource(resources.ModelResource):
    class Meta:
        model = ventapollos
        fields = ('id', 'fecha', 'ubicacion', 'ValorVenta', 'create_date', 'update_date')
        import_id_fields = ['id']
        skip_unchanged = True
        report_skipped = True
        formats = [XLS, XLSX]

class VentaDiariaRealResource(resources.ModelResource):
    sede = fields.Field(
        column_name='sede',
        attribute='sede',
        widget=widgets.ForeignKeyWidget(Sede, field='nombre')
    )
    categoria = fields.Field(
        column_name='categoria',
        attribute='categoria',
        widget=widgets.ForeignKeyWidget(CategoriaVenta, field='nombre')
    )
    class Meta:
        model = VentaDiariaReal
        fields = ('id', 'sede', 'categoria', 'fecha', 'venta_real')
        import_id_fields = ('sede', 'categoria', 'fecha','venta_real')
        skip_unchanged = True
        report_skipped = True
        formats = [XLS, XLSX]