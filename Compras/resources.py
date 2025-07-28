from import_export import resources
from .models import ArticuloClasificacionTemporal

class ArticuloClasificacionTemporalResource(resources.ModelResource):
    class Meta:
        model = ArticuloClasificacionTemporal
        import_id_fields = ('codigo',)
        fields = (
            'codigo', 'departamento', 'seccion', 'familia', 'subfamilia', 'marca',
            'descripcion', 'descat', 'tipo', 'referencia', 'clasificacion',
            'clasificacion2', 'clasificacion3', 'clasificacion5',
            'unidades_compras', 'importe_compras', 'unidades', 'coste', 'beneficio',
            'importe', 'porcentaje_sv', 'stock_actual', 'valoracion_stock_actual',
        )