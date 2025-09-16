from django.contrib import admin
from django.urls import path
from .models import (OrdenCompra, OrdenCompraLinea, OrdenICGLog, ProcesoClasificacion,
                      ArticuloClasificacionTemporal,
                      ArticuloClasificacionProcesado, 
                      ArticuloClasificacionFinal,
                      ReglaClasificacion, SugeridoLineaCambio)
from django import forms
from django.urls import reverse
from django.utils.html import format_html
from .tasks import cargar_proceso_clasificacion_task, actualizar_clasificaciones_en_icg
from django.contrib import messages
from django.template.response import TemplateResponse
from django.shortcuts import get_object_or_404, redirect
from django.forms import modelformset_factory
from Compras.forms import NuevaClasificacionForm
from django.utils.decorators import method_decorator
from django.contrib.admin.views.decorators import staff_member_required
from .utils import procesar_clasificacion
from presupuesto.utils import formato_dinero_colombiano
from django.db.models.functions import Coalesce
from decimal import Decimal

from .services.kpi_proveedores import calcular_cumplimiento_presupuesto
from .services.icg_integration import enviar_orden_a_icg
# NUEVO: servicio que crea el pedido directamente en ICG
from .services.icg_pedidos import crear_pedido_compra_desde_lote

@admin.register(ReglaClasificacion)
class ReglaClasificacionAdmin(admin.ModelAdmin):
    list_display = ('clase', 'umbral_minimo', 'umbral_maximo', 'activa', 'orden')
    list_editable = ('activa', 'orden')
    list_filter = ('activa', 'clase')

@admin.register(ArticuloClasificacionFinal)
class ArticuloClasificacionFinalAdmin(admin.ModelAdmin):
    list_display = (
        'seccion', 'codigo', 'descripcion', 'referencia',
        'marca', 'clasificacion_actual', 'nueva_clasificacion',
        'resultado_validacion', 'almacen',
    )
    list_display_links = None
    list_filter = ('seccion', 'marca', 'clasificacion_actual','nueva_clasificacion','almacen',)
    search_fields = ('codigo', 'descripcion', 'referencia',)
    ordering = ('seccion', '-codigo')
    change_list_template = "admin/Compras/articuloclasificacionfinal/change_list.html" 

    def changelist_view(self, request, extra_context=None):
        proceso_id = request.GET.get('proceso__id__exact')
        proceso_estado = None
        if proceso_id:
            try:
                proceso = ProcesoClasificacion.objects.get(pk=proceso_id)
                proceso_estado = proceso.estado
                # Redirección automática según el estado del proceso
                if proceso_estado == 'procesado':
                    # Redirigir a la edición de ArticuloClasificacionProcesado
                    opts = ArticuloClasificacionProcesado._meta
                    url = reverse(f'admin:{opts.app_label}_{opts.model_name}_changelist')
                    return redirect(f"{url}?proceso__id__exact={proceso_id}")
                elif proceso_estado == 'extraccion':
                    # Redirigir al admin de procesos para lanzar la carga
                    opts = ProcesoClasificacion._meta
                    url = reverse(f'admin:{opts.app_label}_{opts.model_name}_changelist')
                    self.message_user(request, "El proceso aún no ha sido procesado. Inicie la carga de clasificación.", level=messages.WARNING)
                    return redirect(url)
                elif proceso_estado == 'actualizado':
                    # Permitir ver el finalizado
                    pass
                # Si está en 'confirmado', se queda aquí (final)
            except ProcesoClasificacion.DoesNotExist:
                pass
        if extra_context is None:
            extra_context = {}
        extra_context['proceso_estado'] = proceso_estado
        return super().changelist_view(request, extra_context=extra_context)
    # URLs personalizadas
    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path(
                'ejecutar_actualizacion_icg/',
                self.admin_site.admin_view(self.generar_clasificacion_final),
                name='ejecutar_actualizacion_icg'
            ),
        ]
        return custom_urls + urls

    # Lógica de la acción
    def generar_clasificacion_final(self, request):
        proceso_id = request.GET.get('proceso__id__exact')
        if not proceso_id:
            self.message_user(request, "No se especificó el proceso.", messages.ERROR)
            return redirect(request.META.get('HTTP_REFERER', '..'))

        try:
            proceso = ProcesoClasificacion.objects.get(pk=proceso_id, estado="confirmado")
        except ProcesoClasificacion.DoesNotExist:
            self.message_user(request, "No se encontró el proceso confirmado.", messages.ERROR)
            return redirect(request.META.get('HTTP_REFERER', '..'))

        try:
            # Cambia esto:
            # count, errores = actualizar_clasificaciones_en_icg.delay(proceso)
            # Por esto:
            actualizar_clasificaciones_en_icg.delay(proceso.pk)
            # No puedes obtener count y errores directamente, porque Celery ejecuta la tarea en segundo plano.
            # Si quieres mostrar un mensaje inmediato, solo notifica que la tarea fue encolada:
            self.message_user(request, "Tarea encolada para actualizar artículos en ICG. Recargue para ver el resultado.", messages.INFO)
            # El cambio de estado y mensajes de éxito/error deben manejarse cuando la tarea termine (por ejemplo, usando notificaciones o revisando el estado en la base de datos).
        except Exception as e:
            self.message_user(request, f"Error al subir artículos a ICG: {e}", messages.ERROR)

        # Redirige nuevamente al changelist filtrado
        url = reverse('admin:Compras_articuloclasificacionfinal_changelist')
        return redirect(f"{url}?proceso__id__exact={proceso_id}")

    # Filtro por proceso
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        proceso_id = request.GET.get('proceso__id__exact')
        if proceso_id is not None:
            return qs.filter(proceso_id=proceso_id)
        else:
            return qs.none()

    # Solo lectura total
    def has_module_permission(self, request):
        return False

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def has_view_permission(self, request, obj=None):
        return True

    def get_readonly_fields(self, request, obj=None):
        return [f.name for f in self.model._meta.fields]



@admin.register(ArticuloClasificacionProcesado)
class ArticuloClasificacionProcesadoAdmin(admin.ModelAdmin):
    list_display = (
        'seccion', 'codigo', 'descripcion', 'referencia',
        'marca', 'clasificacion_actual',
        'suma_importe', 'import_number_format', 'suma_unidades',
        'porcentaje_acumulado', 'nueva_clasificacion', 'almacen'
    )
    list_editable = ('nueva_clasificacion',)
    list_filter = (
        'seccion', 'marca', 'clasificacion_actual', 'almacen'
    )
    search_fields = ('codigo', 'descripcion', 'referencia')
    ordering = ('seccion', '-suma_importe', 'almacen')
    change_list_template = "admin/Compras/articuloclasificacionprocesado/change_list.html"


    def import_number_format(self, obj):
        """
        Formatea el campo importe_num a un formato legible.
        """
        return formato_dinero_colombiano(obj.importe_num)
    import_number_format.short_description = 'Importe Formateado'

    def changelist_view(self, request, extra_context=None):
        proceso_id = request.GET.get('proceso__id__exact')
        if proceso_id:
            try:
                proceso = ProcesoClasificacion.objects.get(pk=proceso_id)
                if proceso.estado in ['confirmado', 'actualizado']:
                    # Redirigir automáticamente a la vista final si ya está confirmado o actualizado
                    opts = ArticuloClasificacionFinal._meta
                    url = reverse(f'admin:{opts.app_label}_{opts.model_name}_changelist')
                    return redirect(f"{url}?proceso__id__exact={proceso_id}")
            except ProcesoClasificacion.DoesNotExist:
                pass
        response = super().changelist_view(request, extra_context=extra_context)
        try:
            cl = response.context_data["cl"]
            qs = cl.queryset
        except Exception:
            return response

        # Agrupar por artículo y obtener almacenes únicos
        articulos_pivot = {}
        almacenes_set = set()
        for ln in qs:
            key = ln.codigo_articulo
            if key not in articulos_pivot:
                articulos_pivot[key] = {}
            articulos_pivot[key][ln.nombre_almacen] = ln
            almacenes_set.add(ln.nombre_almacen)
        almacenes_list = sorted(almacenes_set)

        response.context_data["articulos_pivot"] = articulos_pivot
        response.context_data["almacenes_list"] = almacenes_list

        return response

    def has_change_permission(self, request, obj=None):
        # Solo permitir edición si el proceso está en 'procesado'
        proceso_id = request.GET.get('proceso__id__exact')
        if proceso_id:
            try:
                proceso = ProcesoClasificacion.objects.get(pk=proceso_id)
                if proceso.estado != 'procesado':
                    return False
            except ProcesoClasificacion.DoesNotExist:
                return False
        return super().has_change_permission(request, obj=obj)

    def has_add_permission(self, request):
        # No permitir agregar manualmente
        return False

    def has_delete_permission(self, request, obj=None):
        # No permitir borrar manualmente
        return False

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        proceso_id = request.GET.get('proceso__id__exact')
        if proceso_id is not None:
            return qs.filter(proceso_id=proceso_id)
        else:
            return qs.none()

    def has_module_permission(self, request):
        return False
    
    def has_add_permission(self, request):
        return False
    
    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path('generar-clasificacion-final/', self.admin_site.admin_view(self.generar_clasificacion_final), name='generar_clasificacion_final')
        ]
        return custom_urls + urls
    
    def generar_clasificacion_final(self, request):
        proceso_id = request.GET.get('proceso__id__exact')
        if not proceso_id:
            messages.error(request, "No se proporcionó un ID de proceso.")
            return redirect("..")

        from .models import ArticuloClasificacionProcesado, ArticuloClasificacionFinal, ProcesoClasificacion
        from .utils import procesar_clasificacion

        proceso = get_object_or_404(ProcesoClasificacion, pk=proceso_id)

        # Solo permitir si está en estado 'procesado'
        if proceso.estado != 'procesado':
            messages.warning(request, f"El proceso debe estar en estado 'procesado' para confirmar.")
            return redirect("..")

        # Validar si ya tiene artículos finales para evitar duplicados
        if ArticuloClasificacionFinal.objects.filter(proceso=proceso).exists():
            messages.warning(request, f"Ya existen artículos finales para el proceso #{proceso.pk}. No se generaron nuevos.")
        else:
            articulos = ArticuloClasificacionProcesado.objects.filter(proceso=proceso)
            creados = []
            # Identificar artículos nuevos usando el modelo temporal y el campo estado_nuevo
            from .models import ArticuloClasificacionTemporal
            codigos_nuevos = set(ArticuloClasificacionTemporal.objects.filter(proceso=proceso, estado_nuevo='NUEVO').values_list('codigo', flat=True))
            for art in articulos:
                # Si el artículo es nuevo, resultado_validacion=False; si no, lógica original
                if art.codigo in codigos_nuevos:
                    resultado_validacion = False
                else:
                    resultado_validacion = (art.clasificacion_actual == art.nueva_clasificacion)
                final = ArticuloClasificacionFinal(
                    proceso=proceso,
                    seccion=art.seccion,
                    codigo=art.codigo,
                    descripcion=art.descripcion,
                    referencia=art.referencia,
                    marca=art.marca,
                    clasificacion_actual=art.clasificacion_actual,
                    nueva_clasificacion=art.nueva_clasificacion,
                    resultado_validacion=resultado_validacion,
                    almacen=art.almacen,
                    estado_accion="PENDIENTE",
                    usuario=request.user,
                )
                creados.append(final)
            ArticuloClasificacionFinal.objects.bulk_create(creados)
            messages.success(request, f"{len(creados)} artículos finales generados.")

        # Procesar si aún no lo estaba
        if proceso.estado != 'procesado':
            procesar_clasificacion(proceso)
            messages.success(request, "Clasificación procesada correctamente.")
        else:
            messages.warning(request, f"La clasificación ya fue procesada.")
        
        proceso.estado = 'confirmado'
        proceso.save(update_fields=['estado'])
        opts = ArticuloClasificacionFinal._meta
        changelist_url = reverse(f'admin:{opts.app_label}_{opts.model_name}_changelist')
        return redirect(f"{changelist_url}?proceso__id__exact={proceso.pk}")

    



@admin.register(ProcesoClasificacion)
class ProcesoClasificacionAdmin(admin.ModelAdmin):
    list_display = ('proceso_display', 'estado', 'fecha_inicio', 'lanzar_wizard')
    actions = ['ejecutar_carga']

    # NUEVO: helper para detectar proveedor
    def _es_proveedor(self, request) -> bool:
        return bool(getattr(request.user, "perfil_proveedor", None))

    # NUEVO: ocultar módulo del índice para proveedores
    def has_module_permission(self, request):
        if self._es_proveedor(request):
            return False
        return super().has_module_permission(request)

    # NUEVO: bloquear permiso de vista para proveedores
    def has_view_permission(self, request, obj=None):
        if self._es_proveedor(request):
            return False
        return super().has_view_permission(request, obj=obj)

    def has_add_permission(self, request):
        return False
    
    def has_change_permission(self, request, obj=None):
        if obj is not None and obj.estado == 'confirmado':
            return False
        return True

    # NUEVO: devolver queryset vacío a proveedores (defensa adicional)
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if self._es_proveedor(request):
            return qs.none()
        return qs

    def ejecutar_carga(self, request, queryset):
        """
        Acción que inicia la tarea Celery independientemente de la selección.
        """
        # Encolar la tarea una sola vez
        cargar_proceso_clasificacion_task.delay(user_id=request.user.id)
        self.message_user(request, 
            "Tarea encolada: carga de clasificación iniciada.", 
            level=messages.SUCCESS
        )
    ejecutar_carga.short_description = "Iniciar carga de clasificación"

    def proceso_display(self, obj):
        if obj.estado == 'actualizado':
            return format_html(
                '<span style="padding:2px 10px; background:#eee; border-left:6px solid #19b23b; font-weight:bold; color:#19b23b;">{} (FINALIZADO)</span>',
                obj
            )
        return str(obj)
    proceso_display.short_description = 'Proceso'

    def lanzar_wizard(self, obj):
        estado = obj.estado
        proceso_id = obj.pk
        if estado == 'extraccion':
            url = reverse('admin:Compras_procesoclasificacion_procesar', args=[proceso_id])
            texto = 'Procesar Extracción'
        elif estado == 'procesado':
            url = reverse('admin:Compras_articuloclasificacionprocesado_changelist') + f'?proceso__id__exact={proceso_id}'
            texto = 'Ir a Procesado'
        elif estado == 'confirmado':
            url = reverse('admin:Compras_articuloclasificacionfinal_changelist') + f'?proceso__id__exact={proceso_id}'
            texto = 'Ir a Confirmado'
        elif estado == 'actualizado':
            url = reverse('admin:Compras_articuloclasificacionfinal_changelist') + f'?proceso__id__exact={proceso_id}'
            texto = 'Finalizado'
        else:
            url = '#'
            texto = estado.capitalize()

        if estado == 'actualizado':
            return format_html('<span style="color:#aaa;">{}</span>', texto)
        else:
            return format_html(
                '<a class="button" style="background:#19b23b;color:#fff;padding:4px 8px;border-radius:4px;text-decoration:none;" href="{}">{}</a>',
                url, texto
            )
    lanzar_wizard.short_description = 'Acción'

    def get_urls(self):
        urls = super().get_urls()
        custom = [
            path(
                '<int:proceso_id>/procesar/',
                self.admin_site.admin_view(self.procesar_view),
                name='Compras_procesoclasificacion_procesar'
            )
        ]
        return custom + urls

    def procesar_view(self, request, proceso_id, *args, **kwargs):
        # NUEVO: bloquear ingreso directo para proveedores
        if getattr(request.user, 'perfil_proveedor', None):
            self.message_user(request, "Acción no permitida para proveedores.", level=messages.ERROR)
            return redirect('admin:index')

        proceso = get_object_or_404(ProcesoClasificacion, pk=proceso_id)

        # Ejecutar procesar_clasificacion si está en 'extraccion'
        if proceso.estado == 'extraccion':
            procesar_clasificacion(proceso)
            proceso.estado = 'procesado'
            proceso.save(update_fields=['estado'])
            messages.success(request, "Extracción procesada correctamente. Ahora puede editar la clasificación.")

        # Redirigir según el estado actual
        if proceso.estado == 'procesado':
            opts = ArticuloClasificacionProcesado._meta
            changelist_url = reverse(
                'admin:%s_%s_changelist' % (opts.app_label, opts.model_name)
            )
            changelist_url += f'?proceso__id__exact={proceso.pk}'
            return redirect(changelist_url)
        elif proceso.estado == 'confirmado' or proceso.estado == 'actualizado':
            opts = ArticuloClasificacionFinal._meta
            changelist_url = reverse(
                'admin:%s_%s_changelist' % (opts.app_label, opts.model_name)
            )
            changelist_url += f'?proceso__id__exact={proceso.pk}'
            return redirect(changelist_url)
        else:
            opts = ProcesoClasificacion._meta
            changelist_url = reverse(f'admin:{opts.app_label}_{opts.model_name}_changelist')
            return redirect(changelist_url)
        # 3) Redirigir
        return redirect(changelist_url)

#--------------------------------------------------------------
#-------------------------------------------------------------
#--------------------------------------------------------------

from .models import (
    Proveedor, Marca, VendedorPerfil, AsignacionMarcaVendedor,
    ProveedorUsuario, SugeridoLote, SugeridoLinea
)
from django.http import HttpResponse
import csv
from django.utils import timezone
from django.conf import settings
from .services.notifications import (
    notificar_proveedor_lote_enviado,
    notificar_compras_respuesta_proveedor
)
from .services.exports import export_lines_to_xlsx
from django.core.mail import send_mail
from .services.icg_integration import enviar_orden_a_icg
from django.db.models import Sum, Count, Case, When, F, Q, DecimalField
from django.db.models import Exists, OuterRef

# ─────────────────────────────
# Filtros personalizados
# ─────────────────────────────

class RangoSugeridoFilter(admin.SimpleListFilter):
    title = "Rango Sugerido"
    parameter_name = "rng_sug"

    def lookups(self, request, model_admin):
        return [
            ("0", "0"),
            ("1-100", "1 a 100"),
            ("101-500", "101 a 500"),
            ("501-2000", "501 a 2000"),
            ("2001+", "Más de 2000"),
        ]

    def queryset(self, request, qs):
        val = self.value()
        if not val:
            return qs
        if val == "0":
            return qs.filter(sugerido_calculado=0)
        if val == "2001+":
            return qs.filter(sugerido_calculado__gte=2001)
        a, b = val.split("-")
        return qs.filter(sugerido_calculado__gte=int(a), sugerido_calculado__lte=int(b))


class RangoCostoFilter(admin.SimpleListFilter):
    title = "Rango Costo Línea"
    parameter_name = "rng_cost"

    def lookups(self, request, model_admin):
        return [
            ("0", "0"),
            ("1-1M", "1 a 1.000.000"),
            ("1M-5M", "1M a 5M"),
            ("5M+", "Más de 5M"),
        ]

    def queryset(self, request, qs):
        val = self.value()
        if not val:
            return qs
        if val == "0":
            return qs.filter(costo_linea=0)
        if val == "5M+":
            return qs.filter(costo_linea__gte=5_000_000)
        if val == "1-1M":
            return qs.filter(costo_linea__gte=1, costo_linea__lte=1_000_000)
        if val == "1M-5M":
            return qs.filter(costo_linea__gt=1_000_000, costo_linea__lt=5_000_000)
        return qs


# NUEVO: Filtro de Marca limitado al lote actual
class MarcaEnLoteFilter(admin.SimpleListFilter):
    title = "Marca"
    parameter_name = "marca__id__exact"

    def lookups(self, request, model_admin):
        from .models import SugeridoLinea  # evitar import circular en tiempo de carga
        lote_id = request.GET.get("lote__id__exact")
        if lote_id:
            rows = (
                SugeridoLinea.objects
                .filter(lote_id=lote_id, marca__isnull=False)
                .values_list("marca_id", "marca__nombre")
                .distinct()
                .order_by("marca__nombre")
            )
        else:
            # Fallback: limitar a lo presente en el queryset actual del admin
            qs = model_admin.get_queryset(request).filter(marca__isnull=False)
            rows = qs.values_list("marca_id", "marca__nombre").distinct().order_by("marca__nombre")
        return [(mid, name) for mid, name in rows]

    def queryset(self, request, qs):
        val = self.value()
        if val:
            return qs.filter(marca_id=val)
        return qs


# NUEVO: base para filtros de valores distintos dentro del lote
class _BaseEnLoteDistinctFilter(admin.SimpleListFilter):
    title = ""
    parameter_name = ""
    field_name = ""

    def lookups(self, request, model_admin):
        qs = model_admin.get_queryset(request)
        lote_id = request.GET.get("lote__id__exact")
        if lote_id:
            qs = qs.filter(lote_id=lote_id)
        # excluir null/vacío
        qs = qs.exclude(**{f"{self.field_name}__isnull": True}).exclude(**{self.field_name: ""})
        vals = qs.values_list(self.field_name, flat=True).distinct().order_by(self.field_name)
        return [(v, v) for v in vals]

    def queryset(self, request, queryset):
        val = self.value()
        if val:
            return queryset.filter(**{self.field_name: val})
        return queryset

class NombreAlmacenEnLoteFilter(_BaseEnLoteDistinctFilter):
    title = "Almacén"
    parameter_name = "nombre_almacen__exact"
    field_name = "nombre_almacen"

class FamiliaEnLoteFilter(_BaseEnLoteDistinctFilter):
    title = "Familia"
    parameter_name = "familia__exact"
    field_name = "familia"

class SubfamiliaEnLoteFilter(_BaseEnLoteDistinctFilter):
    title = "Subfamilia"
    parameter_name = "subfamilia__exact"
    field_name = "subfamilia"

class ClasificacionEnLoteFilter(_BaseEnLoteDistinctFilter):
    title = "Clasificación"
    parameter_name = "clasificacion__exact"
    field_name = "clasificacion"

class EstadoLineaEnLoteFilter(_BaseEnLoteDistinctFilter):
    title = "Estado línea"
    parameter_name = "estado_linea__exact"
    field_name = "estado_linea"


# ─────────────────────────────
# Inlines / Admins
# ─────────────────────────────

class SugeridoLineaInline(admin.TabularInline):
    model = SugeridoLinea
    extra = 0
    fields = (
       "nombre_almacen", "proveedor", "marca",
        "codigo_articulo", "descripcion",
        "stock_actual", "stock_minimo", "stock_maximo",
        "embalaje",
        "ultimo_costo",
        "sugerido_base",  "sugerido_calculado", "cajas_calculadas",
        "sugerido_interno",
        "costo_linea",
        "clasificacion", "warning_no_multiplo", "warning_incremento_100",
        "estado_linea",
    )
    readonly_fields = (
        "nombre_almacen", "proveedor", "marca",
        "codigo_articulo", "descripcion",
        "stock_actual", "stock_minimo", "stock_maximo",
        "embalaje",
        "ultimo_costo",
        "sugerido_base",  "sugerido_calculado", "cajas_calculadas",
        "costo_linea",
        "clasificacion", "warning_no_multiplo", "warning_incremento_100",
        "estado_linea",
    )


# ─────────────────────────────────────────────────────────────────────
# Admin Lote (con link a “ver líneas del lote”)
# ─────────────────────────────────────────────────────────────────────

@admin.register(SugeridoLote)
class SugeridoLoteAdmin(admin.ModelAdmin):
    list_display = ("id", "nombre", "fecha_extraccion", "estado",
                    "total_lineas", "total_costo", "creado_por", "ver_lineas")
    list_filter = ("estado", "creado_por",)
    search_fields = ("nombre", "id", "creado_por__username")
    date_hierarchy = "fecha_extraccion"
    readonly_fields = ("total_lineas","total_costo", "fecha_extraccion", "estado", 
                       "clasificacion_filtro","numserie","numpedido","subserie","pedidos_icg","creado_por",)
    actions = [
        "accion_enviar_a_proveedor",
        "accion_marcar_confirmado",
        "accion_marcar_completado",
        "accion_exportar_xlsx",
        "accion_recalcular_totales",
        "accion_anular_lote",
        "accion_reabrir_proveedor",
    ]

    @admin.display(description="Ver líneas")
    def ver_lineas(self, obj: SugeridoLote):
        url = reverse("admin:sugeridolinea_por_lote", args=[obj.id])
        return format_html(
            '<a class="button" style="background-color: #28a745; color: white; padding: 5px 10px; '
            'border-radius: 5px; text-decoration: none;" href="{}">Abrir Detalle</a>',
            url
        )

    
    @admin.action(description="Marcar como CONFIRMADO")
    def accion_marcar_confirmado(self, request, qs):
        n = qs.update(estado=SugeridoLote.Estado.CONFIRMADO)
        self.message_user(request, f"{n} lote(s) marcados como CONFIRMADO.", messages.SUCCESS)

    @admin.action(description="Marcar como COMPLETADO")
    def accion_marcar_completado(self, request, qs):
        n = qs.update(estado=SugeridoLote.Estado.COMPLETADO)
        self.message_user(request, f"{n} lote(s) marcados como COMPLETADO.", messages.SUCCESS)
    
    @admin.action(description="Anular Lote")
    def accion_anular_lote(self, request, qs):
        n = qs.update(estado=SugeridoLote.Estado.ANULADO)
        self.message_user(request, f"{n} lote(s) anulados.", messages.SUCCESS)
    
    @admin.action(description="Reabrir proveedor")
    def accion_reabrir_proveedor(self, request, qs):
        bloqueados = qs.filter(estado=SugeridoLote.Estado.COMPLETADO).count()
        actualizados = qs.exclude(estado=SugeridoLote.Estado.COMPLETADO)\
                         .update(estado=SugeridoLote.Estado.ENVIADO)
        if actualizados:
            self.message_user(request, f"{actualizados} lote(s) reabiertos para proveedor.", messages.SUCCESS)
        if bloqueados:
            self.message_user(request, f"{bloqueados} lote(s) no se pueden reabrir porque están en estado COMPLETADO.", messages.WARNING)

    @admin.action(description="Exportar XLSX (lote)")
    def accion_exportar_xlsx(self, request, qs):
        if not qs.exists():
            self.message_user(request, "Selecciona al menos un lote.", messages.WARNING)
            return

        if qs.count() == 1:
            lote = qs.first()
            lineas = SugeridoLinea.objects.filter(lote=lote).select_related("proveedor", "marca", "vendedor")
            filename = f"sugerido_lote_{lote.id}.xlsx"
        else:
            ids = list(qs.values_list("id", flat=True))
            lineas = SugeridoLinea.objects.filter(lote_id__in=ids).select_related("proveedor", "marca", "vendedor")
            filename = "sugerido_lotes_" + "_".join(map(str, ids)) + ".xlsx"

        # ✅ No intentes mutar FKs a str aquí; el exportador hace la conversión segura
        xlsx_bytes, filename = export_lines_to_xlsx(lineas, filename=filename)

        resp = HttpResponse(
            xlsx_bytes,
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        resp["Content-Disposition"] = f'attachment; filename="{filename}"'
        return resp

    # Nuevo: setear creado_por automáticamente
    def save_model(self, request, obj, form, change):
        if not change or not getattr(obj, "creado_por_id", None):
            obj.creado_por = request.user
        super().save_model(request, obj, form, change)

    # NUEVO: solo mostrar 'accion_exportar_xlsx' a usuarios con perfil_proveedor
    def _es_proveedor(self, request) -> bool:
        return bool(getattr(request.user, "perfil_proveedor", None))

    def get_actions(self, request):
        actions = super().get_actions(request)
        if self._es_proveedor(request):
            return {k: v for k, v in actions.items() if k == "accion_exportar_xlsx"}
        return actions

    # NUEVO: detectar vendedor interno
    def _es_vendedor(self, request) -> bool:
        return bool(getattr(request.user, "perfil_vendedor", None))

    # Nuevo: filtrar listado por asignaciones
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        perfil_prov = getattr(request.user, "perfil_proveedor", None)
        if perfil_prov:
            return qs.filter(proveedor=perfil_prov.proveedor)
        perfil_vend = getattr(request.user, "perfil_vendedor", None)
        if perfil_vend:
            return qs.filter(
                Exists(
                    AsignacionMarcaVendedor.objects.filter(
                        vendedor=perfil_vend,
                        proveedor_id=OuterRef("proveedor_id"),
                        marca_id=OuterRef("marca_id"),
                    )
                )
            )
        return qs

    # Nuevo: proteger acceso directo a objetos fuera de las asignaciones
    def has_view_permission(self, request, obj=None):
        base = super().has_view_permission(request, obj=obj)
        if not base:
            return False
        if obj is None:
            return True
        perfil_prov = getattr(request.user, "perfil_proveedor", None)
        if perfil_prov:
            return obj.proveedor_id == getattr(perfil_prov.proveedor, "id", None)
        perfil_vend = getattr(request.user, "perfil_vendedor", None)
        if perfil_vend:
            return AsignacionMarcaVendedor.objects.filter(
                vendedor=perfil_vend,
                proveedor_id=obj.proveedor_id,
                marca_id=obj.marca_id,
            ).exists()
        return True

# ─────────────────────────────────────────────────────────────────────
# Admin Línea con TARJETAS KPI + filtros + permisos por rol/proveedor
# ─────────────────────────────────────────────────────────────────────
@admin.register(SugeridoLinea)
class SugeridoLineaAdmin(admin.ModelAdmin):
    # Usa el app_label real para que Django encuentre la plantilla:
    change_list_template = f"admin/{SugeridoLinea._meta.app_label}/sugeridolinea/change_list.html"

    # ---- VISTA POR DEFECTO (interno). La de proveedor se arma dinámicamente ----
    list_display = (
        "proveedor", "marca", "nombre_almacen", "codigo_articulo", "get_descripcion_corta",
        "stock_actual", "sugerido_calculado", "sugerido_interno",
        "nuevo_sugerido_prov", "descuento_prov_pct", "descuento_prov_pct_2", "descuento_prov_pct_3",
        "presupuesto_proveedor", "costo_linea", "clasificacion", "estado_linea",
    )
    list_display_links = ("codigo_articulo",)
    list_editable = ("sugerido_interno",)            # se ajusta dinámicamente
    ordering = ("-lote__fecha_extraccion", "proveedor", "marca", "codigo_articulo")

    list_filter = (
        NombreAlmacenEnLoteFilter,
        ("proveedor", admin.RelatedOnlyFieldListFilter),
        MarcaEnLoteFilter,
        FamiliaEnLoteFilter,
        SubfamiliaEnLoteFilter,
        ClasificacionEnLoteFilter,
        EstadoLineaEnLoteFilter,
    )
    search_fields = ("codigo_articulo", "referencia")

    # Campos RO comunes
    readonly_fields_base = (
       "nombre_almacen", "proveedor", "marca",
        "referencia", "descripcion",
        "departamento", "seccion", "familia", "subfamilia",
        "stock_actual", "stock_minimo", "stock_maximo",
        "uds_compra_base", "uds_compra_mult", "embalaje",
        "ultimo_costo", "sugerido_base", "factor_almacen",
        "sugerido_calculado", "cajas_calculadas", "costo_linea",
        "clasificacion",
        "estado_linea", 
        "nuevo_sugerido_prov", "descuento_prov_pct", "descuento_prov_pct_2", "descuento_prov_pct_3", "continuidad_activo",
        "nuevo_nombre_prov", "observaciones_prov", "presupuesto_proveedor",
    )

    # Fieldsets por defecto (interno). El de proveedor se arma dinámicamente.
    fieldsets = (
        ("Identificación", {
            "fields": (
                ("lote", "estado_linea"),
                ("cod_almacen", "nombre_almacen"),
                ("proveedor", "marca"),
                ("codigo_articulo", "referencia"),
                ("descripcion",),
                ("departamento", "seccion", "familia", "subfamilia"),
                ("tipo", "clasificacion"),
            )
        }),
        ("Parámetros", {
            "fields": (
                ("stock_actual", "stock_minimo", "stock_maximo"),
                ("uds_compra_base", "uds_compra_mult", "embalaje"),
                ("ultimo_costo",),
                ("sugerido_base", "factor_almacen"),
                ("sugerido_calculado", "cajas_calculadas", "costo_linea"),
            )
        }),
        ("Edición interna (Compras)", {
            "fields": ("sugerido_interno", "ultima_cantidad_pedida")
        }),
        ("Respuesta del proveedor", {"fields": ("continuidad_activo", "nuevo_sugerido_prov", "descuento_prov_pct", "descuento_prov_pct_2", "descuento_prov_pct_3", "nuevo_nombre_prov", "observaciones_prov", "presupuesto_proveedor")}),
        ("Validaciones", {
            "fields": ("warning_no_multiplo", "warning_incremento_100")
        })
    )

    actions = [
        "accion_set_interno_igual_calculado",
        "accion_exportar_csv",
        "accion_exportar_xlsx",
        "accion_proveedor_enviar_respuesta",
    ]
    
    def has_module_permission(self, request):
        return False

    # --------- UTILIDADES DE ROL ----------
    def _es_proveedor(self, request) -> bool:
        # Tener un perfil_proveedor en el user indica que es usuario del proveedor
        return bool(getattr(request.user, "perfil_proveedor", None))

    # --------- LISTA DINÁMICA SEGÚN ROL ----------
    def get_list_display(self, request):
        if self._es_proveedor(request):
            return ("marca", "nombre_almacen", "codigo_articulo", "get_descripcion_corta", "stock_actual",
                    "sugerido_calculado", "nuevo_sugerido_prov", "descuento_prov_pct", "descuento_prov_pct_2", "descuento_prov_pct_3",
                    "presupuesto_proveedor", "costo_linea", "clasificacion", "estado_linea")
        return super().get_list_display(request)

    def get_list_display_links(self, request, list_display):
        if self._es_proveedor(request):
            # Evita conflictos con list_editable
            return ("codigo_articulo",)
        return super().get_list_display_links(request, list_display)

    def cajas_calculadas(self, obj):
        return obj.cajas_calculadas
    cajas_calculadas.short_description = "Cajas Calc."
    cajas_calculadas.admin_order_field = "cajas_calculadas"

    def get_list_filter(self, request):
        base = list(super().get_list_filter(request))
        if self._es_proveedor(request):
            # Elimina el filtro de proveedor aunque sea tupla (('proveedor', RelatedOnlyFieldListFilter), ...)
            base = [
                f for f in base
                if not (f == "proveedor" or (isinstance(f, tuple) and len(f) > 0 and f[0] == "proveedor"))
            ]
        return base

    # NUEVO: limitar el queryset al lote si viene en la URL
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        lote_id = request.GET.get("lote__id__exact")
        if lote_id:
            qs = qs.filter(lote_id=lote_id)
        return qs

    def get_urls(self):
        urls = super().get_urls()
        custom = [
            # NUEVO: ruta legible por lote
            path('<int:lote_id>/', self.admin_site.admin_view(self.changelist_por_lote), name='sugeridolinea_por_lote'),
            path('confirmar-lote-proveedor/<int:lote_id>/', self.admin_site.admin_view(self.confirmar_lote_proveedor), name='confirmar_lote_proveedor'),
            path('confirmar-pedido-icg/<int:lote_id>/', self.admin_site.admin_view(self.confirmar_pedido_icg), name='confirmar_pedido_icg'),
            path('importar-a-icg/<int:lote_id>/', self.admin_site.admin_view(self.importar_a_icg), name='importar_a_icg'),
        ]
        return custom + urls

    # NUEVO: wrapper que fuerza el filtro del lote y delega al changelist
    def changelist_por_lote(self, request, lote_id: int):
        q = request.GET.copy()
        q['lote__id__exact'] = str(lote_id)
        request.GET = q
        # opcional, ayuda a que Django/links reflejen el querystring actual
        request.META['QUERY_STRING'] = q.urlencode()
        return self.changelist_view(request)

    # --- Métodos de acciones personalizadas ---
    def confirmar_lote_proveedor(self, request, lote_id):
        from .models import SugeridoLote
        lote = get_object_or_404(SugeridoLote, pk=lote_id)
        perfil = getattr(request.user, 'perfil_proveedor', None)
        if not perfil:
            self.message_user(request, 'Solo un usuario proveedor puede confirmar el sugerido.', level=messages.ERROR)
            return redirect('..')
        if lote.estado in {SugeridoLote.Estado.CONFIRMADO, SugeridoLote.Estado.COMPLETADO}:
            self.message_user(request, 'El lote ya fue confirmado/completado.', level=messages.INFO)
            return redirect(request.META.get('HTTP_REFERER', '..'))
        # (Opcional) validar que todas las líneas del lote sean del mismo proveedor del perfil
        if not lote.lineas.filter(proveedor=perfil.proveedor).exists():
            self.message_user(request, 'No hay líneas de su proveedor en este lote.', level=messages.WARNING)
            return redirect(request.META.get('HTTP_REFERER', '..'))
        lote.estado = SugeridoLote.Estado.CONFIRMADO
        lote.save(update_fields=['estado'])
        self.message_user(request, f'Lote {lote.id} confirmado correctamente.', level=messages.SUCCESS)
        return redirect(request.META.get('HTTP_REFERER', '..'))

    def confirmar_pedido_icg(self, request, lote_id):
        from .models import SugeridoLote
        lote = get_object_or_404(SugeridoLote, pk=lote_id)
        if getattr(request.user, 'perfil_proveedor', None):
            self.message_user(request, 'Acción solo para usuarios internos.', level=messages.ERROR)
            return redirect('..')
        if lote.estado == SugeridoLote.Estado.COMPLETADO:
            self.message_user(request, 'El lote ya está completado.', level=messages.INFO)
            return redirect(request.META.get('HTTP_REFERER', '..'))
        lote.estado = SugeridoLote.Estado.COMPLETADO
        lote.save(update_fields=['estado'])
        self.message_user(request, f'Lote {lote.id} marcado como COMPLETADO (informativo).', level=messages.SUCCESS)
        return redirect(request.META.get('HTTP_REFERER', '..'))

    def importar_a_icg(self, request, lote_id):
        """Genera el pedido en ICG (PEDCOMPRACAB + PEDCOMPRALIN) usando el servicio crear_pedido_compra_desde_lote."""
        from .models import SugeridoLote
        lote = get_object_or_404(SugeridoLote, pk=lote_id)

        # Solo usuarios internos
        if getattr(request.user, 'perfil_proveedor', None):
            self.message_user(request, 'Acción solo para usuarios internos.', level=messages.ERROR)
            return redirect('..')

        try:
            kwargs = {}
            if getattr(lote, "numserie", None):
                kwargs["numserie"] = lote.numserie
            if getattr(lote, "subserie", None):
                kwargs["subserie_n"] = lote.subserie

            pedidos = crear_pedido_compra_desde_lote(lote_id=lote.id, **kwargs)
            if pedidos:
                resumen = ", ".join([f"{p.get('numserie')}-{p.get('numpedido')}({p.get('cod_almacen')})" for p in pedidos])
                self.message_user(request, f"{len(pedidos)} pedido(s) en ICG generados: {resumen}.", level=messages.SUCCESS)
            else:
                self.message_user(request, "No se generaron pedidos (sin líneas válidas).", level=messages.INFO)
        except Exception as e:
            self.message_user(request, f'Error al generar pedido en ICG: {e}', level=messages.ERROR)
        return redirect(request.META.get('HTTP_REFERER', '..'))

    def changelist_view(self, request, extra_context=None):
        es_proveedor = self._es_proveedor(request)
        original_editable = self.list_editable
        if request.method == 'POST':
            from django.db import transaction
            ids = set()
            for k in request.POST.keys():
                if k.startswith('linea_id_'):
                    try: ids.add(int(k.split('_')[-1]))
                    except: pass
                elif k.startswith((
                    'sugerido_interno_',
                    'nuevo_sugerido_prov_',
                    'descuento_prov_pct_',
                    'descuento_prov_pct_2_',
                    'descuento_prov_pct_3_',
                    'continuidad_activo_',
                    'nuevo_nombre_prov_',
                    'observaciones_prov_',
                    'clasificacion_',           # <-- NUEVO
                )):
                    try: ids.add(int(k.split('_')[-1]))
                    except: pass
            lineas = self.model.objects.filter(pk__in=ids).select_related('lote')
            actualizados = 0
            with transaction.atomic():
                for ln in lineas:
                    cambio = False
                    cla = (ln.clasificacion or '').strip().upper()
                    estado_lote = (getattr(ln.lote,'estado','') or '').strip().upper()
                    estado_linea = (ln.estado_linea or '').strip().upper()
                    if es_proveedor:
                        perfil = getattr(request.user,'perfil_proveedor',None)
                        if not perfil or perfil.proveedor != ln.proveedor:
                            continue
                        if cla == 'I' or estado_linea == 'ORDENADA' or estado_lote in {'CONFIRMADO','COMPLETADO'}:
                            continue
                        pid = ln.pk
                        def _dec(v):
                            if v in (None,'','None'): return None
                            try: return Decimal(str(v).replace(',','.'))
                            except: return None
                        m_nsug = request.POST.get(f'nuevo_sugerido_prov_{pid}')
                        m_d1 = request.POST.get(f'descuento_prov_pct_{pid}')
                        m_d2 = request.POST.get(f'descuento_prov_pct_2_{pid}')
                        m_d3 = request.POST.get(f'descuento_prov_pct_3_{pid}')
                        m_cont = request.POST.get(f'continuidad_activo_{pid}')
                        m_nom = request.POST.get(f'nuevo_nombre_prov_{pid}')
                        m_obs = request.POST.get(f'observaciones_prov_{pid}')
                        v_nsug = _dec(m_nsug)
                        if v_nsug is not None and v_nsug != ln.nuevo_sugerido_prov:
                            ln.nuevo_sugerido_prov = v_nsug; cambio = True
                        v_d1 = _dec(m_d1)
                        if v_d1 is not None and v_d1 != ln.descuento_prov_pct:
                            ln.descuento_prov_pct = v_d1; cambio = True
                        v_d2 = _dec(m_d2)
                        if v_d2 is not None and v_d2 != ln.descuento_prov_pct_2:
                            ln.descuento_prov_pct_2 = v_d2; cambio = True
                        v_d3 = _dec(m_d3)
                        if v_d3 is not None and v_d3 != ln.descuento_prov_pct_3:
                            ln.descuento_prov_pct_3 = v_d3; cambio = True
                        v_cont = bool(m_cont)
                        if v_cont != ln.continuidad_activo:
                            ln.continuidad_activo = v_cont; cambio = True
                        if m_nom is not None and m_nom != ln.nuevo_nombre_prov:
                            ln.nuevo_nombre_prov = m_nom; cambio = True
                        if m_obs is not None and m_obs != ln.observaciones_prov:
                            ln.observaciones_prov = m_obs; cambio = True
                        # Propagar descuentos a todas las líneas del mismo código (agrupador)
                        if any(x is not None for x in [v_d1, v_d2, v_d3]):
                            hermanos = self.model.objects.filter(lote_id=ln.lote_id, codigo_articulo=ln.codigo_articulo).exclude(pk=ln.pk)
                            for h in hermanos:
                                h_cambio = False
                                if v_d1 is not None and h.descuento_prov_pct != v_d1:
                                    h.descuento_prov_pct = v_d1; h_cambio = True
                                if v_d2 is not None and h.descuento_prov_pct_2 != v_d2:
                                    h.descuento_prov_pct_2 = v_d2; h_cambio = True
                                if v_d3 is not None and h.descuento_prov_pct_3 != v_d3:
                                    h.descuento_prov_pct_3 = v_d3; h_cambio = True
                                if h_cambio:
                                    h.save(update_fields=['descuento_prov_pct','descuento_prov_pct_2','descuento_prov_pct_3'])
                                    actualizados += 1
                    else:
                        if cla == 'I' or estado_linea == 'ORDENADA' or estado_lote in {'CONFIRMADO','COMPLETADO'}:
                            continue
                        pid = ln.pk
                        # sugerido_interno
                        m_si = request.POST.get(f'sugerido_interno_{pid}')
                        if m_si is not None:
                            try:
                                v_si = Decimal(m_si.replace(',','.'))
                                if v_si != ln.sugerido_interno:
                                    ln.sugerido_interno = v_si; cambio = True
                            except: pass
                        # clasificacion (texto, solo internos)
                        m_clas = request.POST.get(f'clasificacion_{pid}')
                        if m_clas is not None:
                            v_clas = (m_clas or '').strip().upper()
                            if v_clas != (ln.clasificacion or '').strip().upper():
                                ln.clasificacion = v_clas; cambio = True
                    if cambio:
                        ln.save(update_fields=[
                            'clasificacion',                      # <-- NUEVO
                            'nuevo_sugerido_prov','descuento_prov_pct',
                            'descuento_prov_pct_2','descuento_prov_pct_3',
                            'continuidad_activo','nuevo_nombre_prov',
                            'observaciones_prov','sugerido_interno'
                        ])
                        actualizados += 1
            if actualizados:
                self.message_user(request, f"{actualizados} línea(s) actualizada(s).", level=messages.SUCCESS)
            else:
                self.message_user(request, "No hubo cambios aplicables.", level=messages.INFO)
            return redirect(request.get_full_path())
        try:
            response = super().changelist_view(request, extra_context=extra_context)
            try:
                cl = response.context_data["cl"]
                qs = cl.queryset
            except Exception:
                return response

            # NUEVO: si hay filtro por lote, igualar el "total" al resultado filtrado
            if request.GET.get("lote__id__exact"):
                try:
                    cl.full_result_count = cl.result_count
                except Exception:
                    pass

            qty_expr = Case(
                When(sugerido_interno__gt=0, then=F("sugerido_interno")),
                default=F("sugerido_calculado"),
                output_field=DecimalField(max_digits=16, decimal_places=2),
            )
            kpis = qs.aggregate(
                costo_total=Coalesce(Sum("costo_linea"), Decimal("0")),
                total_unidades=Coalesce(Sum(qty_expr), Decimal("0")),
                total_cajas=Coalesce(Sum("cajas_calculadas"), Decimal("0")),
                total_articulos=Count("referencia", distinct=True),
                articulos_con_pedido=Count(Case(When(Q(sugerido_interno__gt=0) | Q(sugerido_calculado__gt=0), then=1))),
                presupuesto_total=Coalesce(Sum("presupuesto_proveedor"), Decimal("0")),
                costo_sugerido_prov=Coalesce(Sum(F("nuevo_sugerido_prov") * F("ultimo_costo")), Decimal("0")),
                costo_sugerido_interno=Coalesce(Sum(F("sugerido_interno") * F("ultimo_costo")), Decimal("0")),
            )
            kpis["costo_promedio_por_articulo"] = (kpis["costo_total"] / kpis["articulos_con_pedido"] if kpis["articulos_con_pedido"] else Decimal("0"))
            kpis["gap_interno_vs_calc"] = kpis["costo_sugerido_interno"] - kpis["costo_total"]
            kpis["gap_prov_vs_calc"] = kpis["costo_sugerido_prov"] - kpis["costo_total"]
            # Cumplimiento presupuesto (% de costo sugerido proveedor sobre presupuesto total)
            kpis["cumplimiento_presupuesto_pct"] = calcular_cumplimiento_presupuesto(proveedor_id=6)
            # KPI adicional: % líneas con descuento >0
            kpis["lineas_con_algún_descuento_pct"] = (qs.filter(Q(descuento_prov_pct__gt=0) | Q(descuento_prov_pct_2__gt=0) | Q(descuento_prov_pct_3__gt=0)).count() / (kpis["total_articulos"] or 1)) * 100
            response.context_data["kpis"] = kpis

            articulos_pivot = {}
            almacenes_set = set()
            for ln in qs:
                key = ln.codigo_articulo
                if key not in articulos_pivot:
                    articulos_pivot[key] = {}
                articulos_pivot[key][ln.nombre_almacen] = ln
                almacenes_set.add(ln.nombre_almacen)
            # Orden personalizado de almacenes
            orden_almacenes = [
                "MERCASUR CALDAS",
                "MERCASUR CENTRO",
                "MERCASUR CABECERA",
                "MERCASUR SOTOMAYOR"
            ]
            almacenes_list = sorted(
                almacenes_set,
                key=lambda x: orden_almacenes.index(x) if x in orden_almacenes else 99
            )
            response.context_data["articulos_pivot"] = articulos_pivot
            response.context_data["almacenes_list"] = almacenes_list
            # Después de response.context_data["es_proveedor"] = es_proveedor (ya abajo) añadimos lote_id_actual
            lote_id = request.GET.get('lote__id__exact')
            if not lote_id:
                ids = list(qs.values_list('lote_id', flat=True).distinct())
                if len(ids) == 1:
                    lote_id = ids[0]
            response.context_data['lote_id_actual'] = lote_id
            response.context_data['es_proveedor'] = es_proveedor

            # NUEVO: estado del lote, flags de UI y bloqueo por grupo 'perfil_vendedor'
            lote_estado = None
            inputs_disabled = False
            if lote_id:
                try:
                    lote_obj = SugeridoLote.objects.only('estado').get(pk=lote_id)
                    lote_estado = lote_obj.estado
                    # Regla original: COMPLETADO deshabilita para todos
                    inputs_disabled = (str(lote_estado).upper() == 'COMPLETADO')
                    # Extra: para usuarios del grupo 'perfil_vendedor', bloquear también en CONFIRMADO
                    es_vendedor_grupo = request.user.groups.filter(name='perfil_vendedor').exists()
                    if es_vendedor_grupo and str(lote_estado).upper() in {'CONFIRMADO', 'COMPLETADO'}:
                        inputs_disabled = True
                    # Ocultar botón "Confirmar Sugerido" a proveedor cuando ya está confirmado/completado
                    response.context_data['ocultar_boton_confirmar_proveedor'] = str(lote_estado).upper() in {'CONFIRMADO', 'COMPLETADO'}
                except SugeridoLote.DoesNotExist:
                    # A falta de lote, no se oculta botón ni se bloquea por estado
                    response.context_data['ocultar_boton_confirmar_proveedor'] = False

            response.context_data['lote_estado'] = lote_estado
            response.context_data['inputs_disabled'] = inputs_disabled

            return response
        finally:
            self.list_editable = original_editable

    def get_descripcion_corta(self, obj):
        txt = getattr(obj, 'descripcion', '') or ''
        return txt if len(txt) <= 50 else txt[:47] + '…'
    get_descripcion_corta.short_description = "Descripción"

# Catálogos
class AsignacionMarcaVendedorInline(admin.TabularInline):
    model = AsignacionMarcaVendedor
    extra = 1
    autocomplete_fields = ("marca", "vendedor",)  # asumiendo FK
    # Si quieres limitar marcas/vendedores por tenant o permisos, usa formfield_for_foreignkey

class ProveedorUsuarioInline(admin.TabularInline):
    model = ProveedorUsuario
    extra = 1
    autocomplete_fields = ("user",)

@admin.register(Proveedor)
class ProveedorAdmin(admin.ModelAdmin):
    list_display = ("nombre","presupuesto_mensual", "nit", "email_contacto", "activo")
    search_fields = ("nombre", "nit")
    list_filter = ("activo",)
    inlines = [AsignacionMarcaVendedorInline, ProveedorUsuarioInline]
    # Opcional: agrupar campos
    fieldsets = (
        ("Identificación", {"fields": ("nombre", "nit", "presupuesto_mensual", "activo")}),
        ("Contacto", {"fields": ("email_contacto",)}),
    )


@admin.register(Marca)
class MarcaAdmin(admin.ModelAdmin):
    list_display = ("nombre",)
    search_fields = ("nombre",)
    def has_module_permission(self, request):
        # Esto oculta "Marcas" del índice del admin
        return False

@admin.register(VendedorPerfil)
class VendedorPerfilAdmin(admin.ModelAdmin):
    list_display = ("user", "alias")
    search_fields = ("user__username", "alias")
    autocomplete_fields = ("user",)
    def has_module_permission(self, request):
        return False

@admin.register(AsignacionMarcaVendedor)
class AsignacionMarcaVendedorAdmin(admin.ModelAdmin):
    list_display = ("proveedor","marca","vendedor")
    list_filter = ("proveedor","marca","vendedor")
    search_fields = ("proveedor__nombre","marca__nombre","vendedor__user__username")
    def has_module_permission(self, request):
        return False

@admin.register(ProveedorUsuario)
class ProveedorUsuarioAdmin(admin.ModelAdmin):
    list_display = ("user","proveedor")
    search_fields = ("user__username","proveedor__nombre")
    autocomplete_fields = ("user","proveedor")
    def has_module_permission(self, request):
        return False