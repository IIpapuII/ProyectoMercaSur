from django.contrib import admin
from .models import SQLQuery, Articulos, DescuentoDiario, APILogRappi
from .views import import_from_csv
from django.urls import reverse
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from django.urls import path
# Register your models here.
@admin.register(SQLQuery)
class SQLQueryAdmin(admin.ModelAdmin):
    values = ['id','nombre', 'consulta', 'descripcion', 'fecha_creacion']
    fields = ['nombre', 'consulta', 'descripcion']
    list_display = values
    search_fields = values

@admin.register(Articulos)
class ArticulosAdmin(admin.ModelAdmin):
    values = ['id_articulo','store_id','ean','name','trademark','price','stock','sale_type','is_available','code']
    fields = ['id_articulo','store_id','name','trademark','description','price','discount_price','stock','sale_type','is_available','departamento','secciones','familia','subfamilia','code','image']
    list_display = values
    search_fields = values
    paginate_by = 10

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path('import-csv/', self.admin_site.admin_view(import_from_csv), name='import-csv'),
        ]
        return custom_urls + urls

    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}
        extra_context['import_csv_url'] = reverse('admin:import-csv')  # Pasar la URL a la plantilla
        return super().changelist_view(request, extra_context=extra_context)

@admin.register(DescuentoDiario)
class DescuentoDiarioAdmin(admin.ModelAdmin):
    values = ['dia','departamento','secciones','familia','porcentaje_descuento']
    fields = ['dia','departamento','secciones','familia','porcentaje_descuento']
    list_display = values
    search_fields = values

@admin.register(APILogRappi)
class APILogRappiAdmin(admin.ModelAdmin):
    values = ['store_id','status_code','response_text','fecha']
    fields = ['store_id','status_code','response_text']
    list_display = values
    search_fields = values

admin.site.site_header = "MercaSur"
admin.site.site_title = "MercaSur"
admin.site.index_title = "Bienvenido a MercaSur"