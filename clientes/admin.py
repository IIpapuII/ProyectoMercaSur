from django.contrib import admin, messages

from service.clientICG import crearClienteICG, getClienteICG
from .models import RegistroCliente, ZonaPermitida, barrio, CodigoTemporal, SecuenciaCodCliente
from import_export.admin import ImportExportModelAdmin
from import_export import resources
from import_export.fields import Field
from import_export.widgets import DateWidget
from import_export.formats.base_formats import XLS, XLSX
from django.db import transaction



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

def _extraer_codcliente(resultado):
    try:
        return resultado[0][0] if resultado and resultado[0] else None
    except Exception:
        return None

def _cod_valido(cod):
    if cod is None:
        return False
    s = str(cod).strip().lower()
    return s not in {"", "0", "none", "null"}

def _flash_chunked(modeladmin, request, lines, level=messages.INFO, chunk=10, prefix=""):
    """
    Evita saturar la UI: envía mensajes en grupos de N líneas.
    """
    if not lines:
        return
    for i in range(0, len(lines), chunk):
        bloque = lines[i:i+chunk]
        texto = prefix + " " + " | ".join(bloque)
        modeladmin.message_user(request, texto, level=level)

@admin.action(description="Enviar a ICG y marcar como creado desde admin")
def action_crear_desde_admin(modeladmin, request, queryset):
    exitosos = 0
    fallidos = 0

    # Detalles para mostrar al final
    detalles_ok = []       # ["doc → codcliente 12345", ...]
    detalles_err = []      # ["doc → error ...", ...]
    detalles_sync = []     # ["doc → sincronizado (ya existía) cod 12345", ...]

    # Recorremos por PK para asegurar atomicidad por fila si luego quieres agregar select_for_update()
    pks = list(queryset.values_list("pk", flat=True))

    for pk in pks:
        try:
            with transaction.atomic():
                cliente = queryset.model.objects.get(pk=pk)

                # 1) Consultar SIEMPRE
                existe = getClienteICG(cliente.numero_documento)
                cod_icg = _extraer_codcliente(existe)

                if _cod_valido(cod_icg):
                    # Ya existe en ICG: sincronizar
                    cambios = []
                    if cliente.codcliente != cod_icg:
                        cliente.codcliente = cod_icg
                        cambios.append("codcliente")
                    if not cliente.creadoICG:
                        cliente.creadoICG = True
                        cambios.append("creadoICG")
                    if not cliente.creado_desde_admin:
                        cliente.creado_desde_admin = True
                        cambios.append("creado_desde_admin")
                    if cambios:
                        cliente.save(update_fields=cambios)

                    exitosos += 1
                    detalles_sync.append(f"{cliente.numero_documento} → sincronizado (cod {cod_icg})")
                    # Mensaje inmediato (opcional)
                    # modeladmin.message_user(request, f"{cliente.numero_documento} sincronizado (cod {cod_icg})", level=messages.SUCCESS)
                    continue

                # 2) No existe: crear SOLO si aplica tu regla
                if cliente.creado_desde_fisico and not cliente.creado_desde_admin:
                    modeladmin.message_user(request, f"{cliente.numero_documento} → creando en ICG…", level=messages.INFO)
                    resultado = crearClienteICG(cliente)
                    print(resultado)
                    if not resultado.get("ok"):
                        # NO marcar flags aquí; crearClienteICG ya es defensiva
                        fallidos += 1
                        err = resultado
                        detalles_err.append(f"{cliente.numero_documento} → {err}")
                        # Mensaje inmediato (opcional)
                        # modeladmin.message_user(request, f"{cliente.numero_documento} → {err}", level=messages.ERROR)
                        continue

                    # Re-consultar para obtener/confirmar codcliente
                    existe2 = getClienteICG(cliente.numero_documento)
                    cod_icg2 = _extraer_codcliente(existe2)

                    if _cod_valido(cod_icg2):
                        cambios = []
                        if cliente.codcliente != cod_icg2:
                            cliente.codcliente = cod_icg2
                            cambios.append("codcliente")
                        if not cliente.creadoICG:
                            cliente.creadoICG = True
                            cambios.append("creadoICG")
                        if not cliente.creado_desde_admin:
                            cliente.creado_desde_admin = True
                            cambios.append("creado_desde_admin")
                        if cambios:
                            cliente.save(update_fields=cambios)

                        exitosos += 1
                        detalles_ok.append(f"{cliente.numero_documento} → creado (cod {cod_icg2})")
                        # modeladmin.message_user(request, f"{cliente.numero_documento} creado (cod {cod_icg2})", level=messages.SUCCESS)
                    else:
                        fallidos += 1
                        detalles_err.append(f"{cliente.numero_documento} → creado pero sin código leído")
                        # modeladmin.message_user(request, f"{cliente.numero_documento} creado pero sin código leído", level=messages.WARNING)
                    continue

                # 3) No existe y no cumple creación automática
                fallidos += 1
                detalles_err.append(f"{cliente.numero_documento} → no cumple criterio de creación (marcar desde físico primero)")

        except Exception as e:
            fallidos += 1
            detalles_err.append(f"{pk} → excepción: {e}")

    # ---- MENSAJES EN ADMIN ----
    if exitosos:
        modeladmin.message_user(request, f"Procesados correctamente {exitosos} cliente(s).", level=messages.SUCCESS)
    if detalles_sync:
        _flash_chunked(modeladmin, request, detalles_sync, level=messages.SUCCESS, prefix="Sincronizados:")
    if detalles_ok:
        _flash_chunked(modeladmin, request, detalles_ok, level=messages.SUCCESS, prefix="Creados:")

    if fallidos:
        modeladmin.message_user(request, f"No se pudieron procesar {fallidos} cliente(s).", level=messages.WARNING)
    if detalles_err:
        _flash_chunked(modeladmin, request, detalles_err, level=messages.WARNING, prefix="Pendientes/errores:")


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