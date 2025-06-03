from django.contrib import admin, messages

from service.clientICG import crearClienteICG
from .models import RegistroCliente, ZonaPermitida, barrio, CodigoTemporal, SecuenciaCodCliente
from import_export.admin import ImportExportModelAdmin
from import_export import resources
from import_export.fields import Field
from import_export.widgets import DateWidget
from import_export.formats.base_formats import XLS, XLSX

@admin.register(SecuenciaCodCliente)
class SecuenciaCodClienteAdmin(admin.ModelAdmin):
    list_display = ('id', 'ultimo_codigo', 'rango_maximo')
    search_fields = ('id',)
    ordering = ('id',)
    list_per_page = 20
    list_filter = ('id',)

@admin.register(CodigoTemporal)
class CodigoTemporalAdmin(admin.ModelAdmin):
    pass

@admin.action(description="Enviar a ICG y marcar como creado desde admin")
def action_crear_desde_admin(modeladmin, request, queryset):
    exitosos = 0
    fallidos = 0

    for cliente in queryset:
        if cliente.creado_desde_fisico and not cliente.creado_desde_admin:
            try:
                crearClienteICG(cliente)
                cliente.refresh_from_db()

                if cliente.codcliente:
                    cliente.creado_desde_admin = True
                    cliente.creadoICG = True
                    cliente.save(update_fields=["creado_desde_admin", "creadoICG"])
                    exitosos += 1
                else:
                    fallidos += 1
            except Exception as e:
                fallidos += 1
        else:
            fallidos += 1

    if exitosos:
        modeladmin.message_user(
            request,
            f"Se procesaron correctamente {exitosos} cliente(s).",
            level=messages.SUCCESS,
        )
    if fallidos:
        modeladmin.message_user(
            request,
            f"No se pudieron procesar {fallidos} cliente(s) (ya creados o error).",
            level=messages.WARNING,
        )


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
    search_fields = ('primer_nombre', 'primer_apellido', 'numero_documento','codcliente' )
    list_filter = ('creado_desde_fisico','creado_desde_admin','creadoICG','fidelizacion', 'tipocliente' , 'punto_compra')
    ordering = ('-fecha_registro',)
    date_hierarchy = 'fecha_registro'
    list_per_page = 20
    actions = [action_crear_desde_admin]

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