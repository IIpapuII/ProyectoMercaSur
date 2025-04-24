from django.contrib import admin
from .models import RegistroCliente, ZonaPermitida, barrio
from import_export.admin import ImportExportModelAdmin
from import_export import resources
from import_export.fields import Field
from import_export.widgets import DateWidget
from import_export.formats.base_formats import XLS, XLSX
# Register your models here.

@admin.register(RegistroCliente)
class RegistroClienteAdmin(admin.ModelAdmin):
    list_display = (
        'primer_nombre',
        'primer_apellido',
        'numero_documento',
        'correo',
        'telefono',
        'celular',
        'mascota',
        'fecha_registro'
    )
    search_fields = ('primer_nombre', 'primer_apellido', 'numero_documento')
    list_filter = ('mascota', 'preferencias_email', 'preferencias_whatsapp', 'preferencias_sms')
    ordering = ('-fecha_registro',)
    date_hierarchy = 'fecha_registro'
    list_per_page = 20

@admin.register(ZonaPermitida)
class ZonaPermitidaAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'latitude',
        'longitude',
        'max_distance',
    )
    search_fields = ('latitude', 'longitude')
    ordering = ('id',)
    list_per_page = 20



class barrioResource(resources.ModelResource):
    nombre = Field(attribute='nombre')

    class Meta:
        model = barrio
        fields = ('nombre')
        formats = [XLS, XLSX]
        import_id_fields = ['nombre']
        export_id_fields = ['nombre']
        skip_unchanged = True
        report_skipped = True

@admin.register(barrio)
class barrioAdmin(ImportExportModelAdmin):
    resource_class = barrioResource
    values = ['id', 'nombre']
    list_display = (
        'id',
        'nombre',
    )
    search_fields = ('nombre',)
    ordering = ('id',)
    list_per_page = 20
    list_filter = ('nombre',)