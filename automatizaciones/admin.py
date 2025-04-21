from django.contrib import admin
from .models import *
from .views import import_from_csv
from django.urls import reverse
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from django.urls import path
from import_export.admin import ExportMixin, ImportExportModelAdmin
from import_export.widgets import DateWidget
from import_export import resources, fields
from import_export.formats.base_formats import XLS, XLSX
# Register your models here.
@admin.register(SQLQuery)
class SQLQueryAdmin(admin.ModelAdmin):
    values = ['id','nombre', 'consulta', 'descripcion', 'fecha_creacion']
    fields = ['nombre', 'consulta', 'descripcion']
    list_display = values
    search_fields = values

class ArticulosResource(resources.ModelResource):
    ean = fields.Field(column_name='ean', attribute='ean')
    name = fields.Field(column_name='name', attribute='name')
    trademark = fields.Field(column_name='trademark', attribute='trademark')
    price = fields.Field(column_name='price', attribute='price')
    stock = fields.Field(column_name='stock', attribute='stock')
    sale_type = fields.Field(column_name='sale_type', attribute='sale_type')
    discount_price = fields.Field(column_name='discount_price', attribute='discount_price')
    is_available = fields.Field(column_name='is_available', attribute='is_available')

    class Meta:
        model = Articulos
        formats = [XLS, XLSX]
        import_id_fields = ['ean']  
        fields = ['store_id','ean', 'name', 'trademark', 'price', 'stock', 'sale_type', 'discount_price', 'is_available','tarifa','departamento','secciones','familia','subfamilia','code']
        export_order = ['store_id','ean', 'name', 'trademark', 'price', 'stock', 'sale_type', 'discount_price', 'is_available','tarifa','departamento','secciones','familia','subfamilia','code']
        skip_unchanged = True  
        report_skipped = True

@admin.register(Articulos)
class ArticulosAdmin(ImportExportModelAdmin):
    resource_class = ArticulosResource
    values = ['id_articulo','store_id','ean','name','trademark','price','stock','sale_type','discount_price','is_available','code']
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

class DescuentoDiarioResource(resources.ModelResource):
    ean = fields.Field(column_name='ean', attribute='ean')
    porcentaje_descuento = fields.Field(column_name='porcentaje_descuento', attribute='porcentaje_descuento')
    fecha_inicio = fields.Field(column_name='fecha_inicio', attribute='fecha_inicio', widget=DateWidget(format='%Y-%m-%d'))
    fecha_fin = fields.Field(column_name='fecha_fin', attribute='fecha_fin', widget=DateWidget(format='%Y-%m-%d'))

    class Meta:
        model = DescuentoDiario
        formats = [XLS, XLSX]
        import_id_fields = ['ean']  
        fields = ['ean', 'porcentaje_descuento', 'fecha_inicio', 'fecha_fin', 'destacado','maximo_venta']
        export_order = ['ean', 'porcentaje_descuento', 'fecha_inicio', 'fecha_fin', 'destacado','maximo_venta']
        skip_unchanged = True  
        report_skipped = True  

@admin.register(DescuentoDiario)
class DescuentoDiarioAdmin(ImportExportModelAdmin):
    resource_class = DescuentoDiarioResource
    values = ['dia', 'Trademark','departamento', 'secciones', 'familia', 'ean', 'porcentaje_descuento', 'fecha_inicio', 'fecha_fin', 'destacado','maximo_venta', 'activo']
    fields = values  
    list_display = values  
    search_fields = ['departamento', 'secciones', 'familia', 'ean']  
    list_filter = ['dia', 'fecha_inicio', 'fecha_fin'] 
    ordering = ['fecha_inicio', 'fecha_fin']  
    date_hierarchy = 'fecha_inicio'  

@admin.register(APILogRappi)
class APILogRappiAdmin(admin.ModelAdmin):
    values = ['store_id','status_code','response_text','fecha']
    fields = ['store_id','status_code','response_text']
    list_display = values
    search_fields = values

#########################Crear Articulos #########################
class PresentationInline(admin.StackedInline):
    model = Presentation
    extra = 1  

class SellTypeInline(admin.StackedInline):
    model = SellType
    extra = 1  

class ProductSKUInline(admin.StackedInline):
    model = ProductSKU
    extra = 1 
    show_change_link = True

class ProductImageInline(admin.StackedInline):
    model = ProductImage
    extra = 1 

class ProductAttributeInline(admin.StackedInline):
    model = ProductAttribute
    extra = 1  


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    inlines = [PresentationInline, SellTypeInline, ProductSKUInline]
    list_display = ("name", "category_id", "has_variation")
    search_fields = ("name", "category_id")
    list_filter = ("has_variation",)

@admin.register(ProductSKU)
class ProductSKUAdmin(admin.ModelAdmin):
    inlines = [ProductImageInline, ProductAttributeInline]
    list_display = ("sku", "ean", "product")
    search_fields = ("sku", "ean")

@admin.register(EnvioLog)
class EnvioLogAdmin(admin.ModelAdmin):
    pass

admin.site.site_header = "mercasur"
admin.site.site_title = "mercasur"
admin.site.index_title = "Bienvenido a mercasur"