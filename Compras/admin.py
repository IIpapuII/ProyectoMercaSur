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
            result = actualizar_clasificaciones_en_icg.delay(proceso.pk)
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
        return super().changelist_view(request, extra_context=extra_context)

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
            for art in articulos:
                final = ArticuloClasificacionFinal(
                    proceso=proceso,
                    seccion=art.seccion,
                    codigo=art.codigo,
                    descripcion=art.descripcion,
                    referencia=art.referencia,
                    marca=art.marca,
                    clasificacion_actual=art.clasificacion_actual,
                    nueva_clasificacion=art.nueva_clasificacion,
                    resultado_validacion=(art.clasificacion_actual == art.nueva_clasificacion),  # lógica personalizada si deseas
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

    def has_add_permission(self, request):
        return False
    
    def has_change_permission(self, request, obj=None):
        if obj is not None and obj.estado == 'confirmado':
            return False
        return True

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
            # Por defecto, redirigir al listado de procesos
            opts = ProcesoClasificacion._meta
            changelist_url = reverse(f'admin:{opts.app_label}_{opts.model_name}_changelist')
            return redirect(changelist_url)
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
from .services.exports import export_lines_to_xlsx, render_orden_compra_pdf
from django.core.mail import send_mail
from .services.icg_integration import enviar_orden_a_icg
from django.db.models import Sum, Count, Case, When, F, Q, DecimalField

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
    list_display = ("id", "nombre", "fecha_extraccion", "estado", "clasificacion_filtro",
                    "total_lineas", "total_costo", "creado_por", "ver_lineas")
    list_filter = ("estado", "clasificacion_filtro")
    search_fields = ("nombre", "id", "creado_por__username")
    date_hierarchy = "fecha_extraccion"
    actions = [
        "accion_enviar_a_proveedor",
        "accion_marcar_confirmado",
        "accion_marcar_completado",
        "accion_exportar_xlsx",
        "accion_exportar_pdf",
        "accion_exportar_csv",
        "accion_generar_orden_compra",
        "accion_recalcular_totales",
    ]

    @admin.display(description="Ver líneas")
    def ver_lineas(self, obj: SugeridoLote):
        url = (
            reverse("admin:Compras_sugeridolinea_changelist")
            + f"?lote__id__exact={obj.id}"
        )
        return format_html(
        '<a class="button" style="background-color: #28a745; color: white; padding: 5px 10px; '
        'border-radius: 5px; text-decoration: none;" href="{}">Abrir Detalle</a>',
        url
    )


    @admin.action(description="Enviar notificación a proveedor y marcar como ENVIADO")
    def accion_enviar_a_proveedor(self, request, qs):
        for lote in qs:
            provedores = lote.lineas.values_list("proveedor", flat=True).distinct()
            for prov in provedores:
                notificar_proveedor_lote_enviado(proveedor_nombre=prov, lote=lote, request=request)
            lote.estado = SugeridoLote.Estado.ENVIADO
            lote.save(update_fields=["estado"])
        self.message_user(request, "Proveedores notificados y lotes marcados como ENVIADO.", messages.SUCCESS)

    @admin.action(description="Marcar como CONFIRMADO")
    def accion_marcar_confirmado(self, request, qs):
        n = qs.update(estado=SugeridoLote.Estado.CONFIRMADO)
        self.message_user(request, f"{n} lote(s) marcados como CONFIRMADO.", messages.SUCCESS)

    @admin.action(description="Marcar como COMPLETADO")
    def accion_marcar_completado(self, request, qs):
        n = qs.update(estado=SugeridoLote.Estado.COMPLETADO)
        self.message_user(request, f"{n} lote(s) marcados como COMPLETADO.", messages.SUCCESS)

    @admin.action(description="Exportar XLSX (lote)")
    def accion_exportar_xlsx(self, request, qs):
        lote = qs.first()
        if not lote:
            self.message_user(request, "Selecciona un lote.", messages.WARNING)
            return
        wb_bytes, filename = export_lines_to_xlsx(lote.lineas.all(), filename=f"sugerido_lote_{lote.id}.xlsx")
        resp = HttpResponse(wb_bytes, content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        resp["Content-Disposition"] = f'attachment; filename="{filename}"'
        return resp

    @admin.action(description="Exportar PDF (lote)")
    def accion_exportar_pdf(self, request, qs):
        lote = qs.first()
        if not lote:
            self.message_user(request, "Selecciona un lote.", messages.WARNING)
            return
        pdf_bytes, filename = render_orden_compra_pdf(
            encabezado={
                "numero_orden": f"PRE-{lote.id}-{timezone.now().strftime('%Y%m%d')}",
                "proveedor": "Varios",
                "almacen": "Varios",
                "fecha": timezone.now(),
                "costo_total": lote.total_costo,
            },
            lineas=lote.lineas.all()
        )
        resp = HttpResponse(pdf_bytes, content_type="application/pdf")
        resp["Content-Disposition"] = f'attachment; filename="{filename}"'
        return resp

    @admin.action(description="Exportar CSV (lote)")
    def accion_exportar_csv(self, request, qs):
        lote = qs.first()
        if not lote:
            self.message_user(request, "Selecciona un lote.", messages.WARNING)
            return
        response = HttpResponse(content_type="text/csv")
        fn = f"sugerido_lote_{lote.id}_{timezone.now().date()}.csv"
        response["Content-Disposition"] = f'attachment; filename="{fn}"'
        w = csv.writer(response, delimiter=";")
        w.writerow([
            "Proveedor","Marca","Almacén","Código","Descripción",
            "StockAct","StockMin","StockMax",
            "UdsBase","UdsMult","Embalaje",
            "CostoUnit","SugeridoBase","Factor","SugeridoCalc","Cajas","CostoLinea","Clasificación"
        ])
        for ln in lote.lineas.all():
            w.writerow([
                ln.proveedor, (ln.marca or ""),
                f"{ln.cod_almacen}-{ln.nombre_almacen}",
                ln.codigo_articulo, ln.descripcion,
                ln.stock_actual, ln.stock_minimo, ln.stock_maximo,
                ln.uds_compra_base, ln.uds_compra_mult, ln.embalaje,
                ln.ultimo_costo, ln.sugerido_base, ln.factor_almacen,
                ln.sugerido_calculado, ln.cajas_calculadas, ln.costo_linea,
                (ln.clasificacion or "")
            ])
        return response

    @admin.action(description="Generar Orden de Compra (agrupada por Proveedor y Almacén)")
    def accion_generar_orden_compra(self, request, qs):
        from django.db import transaction
        generadas = 0
        for lote in qs:
            grupos = {}
            for ln in lote.lineas.all():
                qty = (ln.sugerido_interno or 0) or (ln.sugerido_calculado or 0)
                if (ln.clasificacion or "").upper() == "I" or qty <= 0:
                    continue
                key = (ln.proveedor, ln.cod_almacen, ln.nombre_almacen)
                grupos.setdefault(key, []).append(ln)

            with transaction.atomic():
                for (prov, codalm, nomalm), lineas in grupos.items():
                    num = f"OC-{lote.id}-{prov[:8]}-{codalm}-{timezone.now().strftime('%H%M%S')}"
                    oc = OrdenCompra.objects.create(
                        lote=lote, proveedor=prov, cod_almacen=codalm, nombre_almacen=nomalm,
                        numero_orden=num, generado_por=request.user
                    )
                    total = Decimal("0")
                    for ln in lineas:
                        qty = (ln.sugerido_interno or 0) or (ln.sugerido_calculado or 0)
                        costo_total = qty * (ln.ultimo_costo or 0)
                        OrdenCompraLinea.objects.create(
                            orden=oc,
                            codigo_articulo=ln.codigo_articulo,
                            descripcion=ln.descripcion,
                            embalaje=ln.embalaje,
                            cantidad=qty,
                            costo_unitario=ln.ultimo_costo,
                            costo_total=costo_total,
                            clasificacion=ln.clasificacion,
                        )
                        total += costo_total
                        ln.estado_linea = SugeridoLinea.EstadoLinea.ORDENADA
                        ln.save(update_fields=["estado_linea", "actualizado"])
                    oc.costo_total = total
                    oc.save(update_fields=["costo_total"])

                    exito, id_icg, msg = enviar_orden_a_icg(oc)
                    OrdenICGLog.objects.create(
                        orden=oc, exito=exito, id_orden_icg=id_icg, mensaje=msg, payload=None
                    )
                    if exito:
                        oc.id_orden_icg = id_icg
                        oc.save(update_fields=["id_orden_icg"])
                    generadas += 1

            lote.estado = SugeridoLote.Estado.COMPLETADO
            lote.save(update_fields=["estado"])

        self.message_user(request, f"{generadas} orden(es) de compra generadas.", messages.SUCCESS)

    @admin.action(description="Recalcular totales del lote")
    def accion_recalcular_totales(self, request, qs):
        for lote in qs:
            lote.recomputar_totales()
        self.message_user(request, "Totales recalculados.", messages.SUCCESS)


# ─────────────────────────────────────────────────────────────────────
# Admin Línea con TARJETAS KPI + filtros + permisos por rol/proveedor
# ─────────────────────────────────────────────────────────────────────
@admin.register(SugeridoLinea)
class SugeridoLineaAdmin(admin.ModelAdmin):
    # Usa el app_label real para que Django encuentre la plantilla:
    change_list_template = f"admin/{SugeridoLinea._meta.app_label}/sugeridolinea/change_list.html"

    # ---- VISTA POR DEFECTO (interno). La de proveedor se arma dinámicamente ----
    list_display = (
        "proveedor", "marca",
         "nombre_almacen",
         "descripcion_corta",
        "stock_actual", "stock_minimo", "stock_maximo",
        "sugerido_calculado","cajas_calculadas", "sugerido_interno",
        "ultimo_costo", "costo_linea",
        "clasificacion", 
        "estado_linea",
        "nuevo_sugerido_prov", "descuento_prov_pct", "continuidad_activo",
                "nuevo_nombre_prov", "observaciones_prov",
    )
    list_display_links = ("lote", "codigo_articulo")  # se ajusta dinámicamente
    list_editable = ("sugerido_interno",)            # se ajusta dinámicamente
    ordering = ("-lote__fecha_extraccion", "proveedor", "marca", "codigo_articulo")

    list_filter = (
        ("lote__fecha_extraccion", admin.DateFieldListFilter),
        "lote__estado",
        ("lote", admin.RelatedOnlyFieldListFilter),
        "cod_almacen", "nombre_almacen",
        "proveedor", "marca",
        "familia", "subfamilia",
        "clasificacion",
        "warning_no_multiplo", "warning_incremento_100",
        "estado_linea",
    )
    search_fields = ("codigo_articulo", "descripcion", "proveedor", "marca", "familia", "subfamilia", "cod_almacen", "nombre_almacen")

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
        "nuevo_sugerido_prov", "descuento_prov_pct", "continuidad_activo",
                "nuevo_nombre_prov", "observaciones_prov",
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
        ("Respuesta del proveedor", {
            "fields": ("continuidad_activo", "nuevo_sugerido_prov", "descuento_prov_pct", "nuevo_nombre_prov", "observaciones_prov")
        }),
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
            # Vista proveedor: solo campos que debe diligenciar + contexto mínimo
            return (
                "marca", "nombre_almacen",
                 "descripcion_corta", "referencia",
                "stock_actual",  # solo lectura
                "sugerido_calculado",
                "embalaje",
                "cajas_calculadas",
                "nuevo_sugerido_prov", "descuento_prov_pct", "continuidad_activo",
                "nuevo_nombre_prov", "observaciones_prov",
                "ultimo_costo", "costo_linea",
                "clasificacion", "estado_linea",
            )
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
            # Proveedor no necesita filtro por proveedor (ya viene filtrado por queryset)
            base = [f for f in base if f not in ("proveedor",)]
        return base

    def changelist_view(self, request, extra_context=None):
        """
        - Ajusta list_editable según rol.
        - Agrega KPIs (con separador de miles en plantilla).
        """
        # 1) Cambiar list_editable según rol (y restaurarlo al salir)
        original_editable = self.list_editable
        if self._es_proveedor(request):
            self.list_editable = ("nuevo_sugerido_prov", "descuento_prov_pct", "continuidad_activo", "nuevo_nombre_prov", "observaciones_prov")
        else:
            self.list_editable = ("sugerido_interno",)

        try:
            response = super().changelist_view(request, extra_context=extra_context)
            # 2) Agregar KPIs
            try:
                cl = response.context_data["cl"]
                qs = cl.queryset
            except Exception:
                return response

            qty_expr = Case(
                When(sugerido_interno__gt=0, then=F("sugerido_interno")),
                default=F("sugerido_calculado"),
                output_field=DecimalField(max_digits=16, decimal_places=2),
            )
            kpis = qs.aggregate(
                costo_total=Coalesce(Sum("costo_linea"), Decimal("0")),
                total_unidades=Coalesce(Sum(qty_expr), Decimal("0")),
                total_cajas=Coalesce(Sum("cajas_calculadas"), Decimal("0")),
                total_articulos=Count("id"),
                articulos_con_pedido=Count(Case(When(Q(sugerido_interno__gt=0) | Q(sugerido_calculado__gt=0), then=1))),
            )
            kpis["costo_promedio_por_articulo"] = (
                (kpis["costo_total"] or 0) / kpis["articulos_con_pedido"]
                if kpis["articulos_con_pedido"] else Decimal("0")
            )
            response.context_data["kpis"] = kpis
            return response
        finally:
            # Restaurar config para no “contaminar” otros requests
            self.list_editable = original_editable

    # --------- CAMPOS EDITABLES/RO POR CLASIFICACIÓN ----------
    def get_readonly_fields(self, request, obj=None):
        """
        Reglas de edición:
        - Lote CONFIRMADO/COMPLETADO => todo read-only.
        - Clasif I => todo read-only.
        - Proveedor: solo A/B, y solo cuando estado_linea sea PENDIENTE o ENVIADA_PROV.
        Nunca puede editar 'sugerido_interno'.
        - Interno:
            * A/B/C => puede editar sugerido_interno y también los campos del proveedor.
            * Otras clasificaciones => sugerido_interno read-only (los del proveedor quedan editables).
            * Si la línea ya está ORDENADA => todo read-only.
        """
        ro = list(getattr(self, "readonly_fields_base", ()))

        # Campos de edición
        campos_prov = [
            "continuidad_activo",
            "nuevo_sugerido_prov",
            "descuento_prov_pct",
            "nuevo_nombre_prov",
            "observaciones_prov",
        ]
        campo_interno = ["sugerido_interno"]

        # Sin objeto (add view): nada se crea manualmente desde aquí → todo RO
        if obj is None:
            return ro + campos_prov + campo_interno

        # Normaliza
        cla = (obj.clasificacion or "").strip().upper()
        estado_linea = (obj.estado_linea or "").strip().upper()
        estado_lote = (getattr(obj.lote, "estado", "") or "").strip().upper()

        perfil = getattr(request.user, "perfil_proveedor", None)
        es_proveedor = bool(perfil and getattr(perfil, "proveedor", None))

        # 1) Bloqueos globales por estado de lote
        if estado_lote in {"CONFIRMADO", "COMPLETADO"}:
            return ro + campos_prov + campo_interno

        # 2) Clasificación I => histórico / consulta
        if cla == "I":
            return ro + campos_prov + campo_interno

        # 3) Bloqueo si la línea ya fue ORDENADA
        if estado_linea in {"ORDENADA"}:
            return ro + campos_prov + campo_interno

        # 4) Reglas por rol
        if es_proveedor:
            # El proveedor NUNCA edita el sugerido_interno
            ro_base = ro + campo_interno

            # Solo A/B y solo si la línea está disponible para edición del proveedor
            if cla in {"A", "B"} and estado_linea in {"PENDIENTE", "ENVIADA_PROV"}:
                # deja editables los campos del proveedor
                return ro_base
            else:
                # bloquea campos del proveedor también
                return ro_base + campos_prov

        # Interno (Compras)
        if cla in {"A", "B", "C"}:
            # puede editar sugerido_interno y también (si lo deseas) los campos del proveedor
            # (no añadimos nada a 'ro')
            return ro

        # Otras clasificaciones: sugerido_interno read-only; resto editable
        return ro + campo_interno
    from django.forms import ModelForm

    def get_changelist_formset(self, request, **kwargs):
        """
        Deshabilita inputs en la tabla (list_editable) según mismas reglas,
        para que las filas se comporten como read-only en UI.
        """
        formset = super().get_changelist_formset(request, **kwargs)
        base_init = formset.form.__init__

        perfil = getattr(request.user, "perfil_proveedor", None)
        es_proveedor = bool(perfil and getattr(perfil, "proveedor", None))

        def _init(formself, *args, **kw):
            base_init(formself, *args, **kw)
            obj = getattr(formself, "instance", None)
            if not obj:
                return

            cla = (obj.clasificacion or "").strip().upper()
            estado_linea = (obj.estado_linea or "").strip().upper()
            estado_lote = (getattr(obj.lote, "estado", "") or "").strip().upper()

            # mismos conjuntos de campos que arriba
            campos_prov = [
                "continuidad_activo",
                "nuevo_sugerido_prov",
                "descuento_prov_pct",
                "nuevo_nombre_prov",
                "observaciones_prov",
            ]
            campo_interno = ["sugerido_interno"]

            def _disable(campos):
                for name in campos:
                    if name in formself.fields:
                        f = formself.fields[name]
                        f.disabled = True
                        f.widget.attrs["readonly"] = "readonly"
                        f.widget.attrs["data-ro-i"] = "1"
                        f.widget.attrs["tabindex"] = "-1"

            # Reglas espejo
            if estado_lote in {"CONFIRMADO", "COMPLETADO"} or cla == "I" or estado_linea in {"ORDENADA"}:
                _disable(campos_prov + campo_interno)
                return

            if es_proveedor:
                # Proveedor nunca edita el sugerido interno
                _disable(campo_interno)
                if not (cla in {"A", "B"} and estado_linea in {"PENDIENTE", "ENVIADA_PROV"}):
                    _disable(campos_prov)
            else:
                # Interno: A/B/C editables; otras clasif => sugerido_interno RO
                if cla not in {"A", "B", "C"}:
                    _disable(campo_interno)

        formset.form.__init__ = _init
        return formset


    # --------- QUERYSET RESTRINGIDO PARA PROVEEDOR ----------
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        perfil_prov = getattr(request.user, "perfil_proveedor", None)
        if perfil_prov:
            qs = qs.filter(proveedor=perfil_prov.proveedor)
        return qs

    # --------- GUARDADO / MENSAJES ----------
    def save_model(self, request, obj, form, change):
        prev_multiplo = obj.warning_no_multiplo
        prev_inc = obj.warning_incremento_100
        super().save_model(request, obj, form, change)
        obj.lote.recomputar_totales()
        if obj.warning_no_multiplo and not prev_multiplo:
            self.message_user(request, "⚠️ El sugerido NO es múltiplo del embalaje.", level=messages.WARNING)
        if obj.warning_incremento_100 and not prev_inc:
            self.message_user(request, "⚠️ Incremento >100% frente al último pedido.", level=messages.WARNING)

    # --------- VARIOS ----------
    @admin.display(description="Descripción")
    def descripcion_corta(self, obj: SugeridoLinea):
        txt = obj.descripcion or ""
        return txt if len(txt) <= 50 else txt[:47] + "…"

    @admin.action(description="(Compras) Setear sugerido interno = sugerido calculado")
    def accion_set_interno_igual_calculado(self, request, queryset):
        if self._es_proveedor(request):
            messages.warning(request, "Acción reservada para Compras.")
            return
        n = 0
        for ln in queryset:
            if (ln.clasificacion or "").strip().upper() == "I":
                continue
            ln.sugerido_interno = ln.sugerido_calculado
            ln.save(update_fields=["sugerido_interno", "actualizado"])
            n += 1
        messages.success(request, f"{n} línea(s) actualizada(s).")

    @admin.action(description="(Proveedor) Enviar respuesta de sugerido")
    def accion_proveedor_enviar_respuesta(self, request, queryset):
        perfil_prov = getattr(request.user, "perfil_proveedor", None)
        if not perfil_prov:
            messages.warning(request, "Acción reservada para proveedores.")
            return
        from .models import SugeridoLineaCambio
        creados = 0
        for ln in queryset:
            if ln.proveedor != perfil_prov.proveedor:
                continue
            SugeridoLineaCambio.objects.create(
                linea=ln, usuario=request.user,
                continuidad_activo=ln.continuidad_activo,
                nuevo_sugerido_prov=ln.nuevo_sugerido_prov,
                descuento_prov_pct=ln.descuento_prov_pct,
                nuevo_nombre_prov=ln.nuevo_nombre_prov,
                observaciones_prov=ln.observaciones_prov,
            )
            ln.estado_linea = SugeridoLinea.EstadoLinea.RESPONDIDA
            ln.save(update_fields=["estado_linea", "actualizado"])
            creados += 1
        if creados:
            notificar_compras_respuesta_proveedor(proveedor_nombre=perfil_prov.proveedor, lineas=queryset, request=request)
        messages.success(request, f"Respuesta enviada. {creados} línea(s) respondida(s).")

    @admin.action(description="Exportar CSV (vista actual)")
    def accion_exportar_csv(self, request, queryset):
        response = HttpResponse(content_type="text/csv")
        fn = f"sugerido_lineas_{timezone.now().date()}.csv"
        response["Content-Disposition"] = f'attachment; filename="{fn}"'
        w = csv.writer(response, delimiter=";")
        w.writerow([
            "Lote","Proveedor","Marca","Almacén","Código","Descripción",
            "StockAct","StockMin","StockMax",
            "UdsBase","UdsMult","Embalaje",
            "CostoUnit","SugeridoBase","Factor","SugeridoCalc",
            "SugeridoInterno","NuevoSugProv","DescProv%","Continuidad","NuevoNombre","Obs",
            "Cajas","CostoLinea","Clasificación",
            "NoMultiplo","Inc>100%"
        ])
        for ln in queryset:
            w.writerow([
                ln.lote_id, ln.proveedor, (ln.marca or ""),
                f"{ln.cod_almacen}-{ln.nombre_almacen}",
                ln.codigo_articulo, ln.descripcion,
                ln.stock_actual, ln.stock_minimo, ln.stock_maximo,
                ln.uds_compra_base, ln.uds_compra_mult, ln.embalaje,
                ln.ultimo_costo, ln.sugerido_base, ln.factor_almacen,
                ln.sugerido_calculado,
                ln.sugerido_interno, ln.nuevo_sugerido_prov, ln.descuento_prov_pct,
                ln.continuidad_activo, (ln.nuevo_nombre_prov or ""), (ln.observaciones_prov or ""),
                ln.cajas_calculadas, ln.costo_linea, (ln.clasificacion or ""),
                ln.warning_no_multiplo, ln.warning_incremento_100
            ])
        return response

    @admin.action(description="Exportar XLSX (vista actual)")
    def accion_exportar_xlsx(self, request, queryset):
        wb_bytes, filename = export_lines_to_xlsx(queryset, filename=f"sugerido_lineas_{timezone.now().strftime('%Y%m%d_%H%M')}.xlsx")
        resp = HttpResponse(wb_bytes, content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        resp["Content-Disposition"] = f'attachment; filename="{filename}"'
        return resp

# Registros (si no los tenías ya)
@admin.register(SugeridoLineaCambio)
class SugeridoLineaCambioAdmin(admin.ModelAdmin):
    list_display = ("linea", "fecha", "usuario", "nuevo_sugerido_prov", "descuento_prov_pct")
    list_filter = ("fecha",)
    search_fields = ("linea__codigo_articulo", "usuario__username")


@admin.register(OrdenCompra)
class OrdenCompraAdmin(admin.ModelAdmin):
    list_display = ("numero_orden", "proveedor", "nombre_almacen", "fecha", "costo_total", "id_orden_icg")
    list_filter = ("fecha", "proveedor", "nombre_almacen")
    search_fields = ("numero_orden", "proveedor", "nombre_almacen")


@admin.register(OrdenCompraLinea)
class OrdenCompraLineaAdmin(admin.ModelAdmin):
    list_display = ("orden", "codigo_articulo", "descripcion", "cantidad", "costo_unitario", "costo_total")
    list_filter = ("orden__proveedor", "orden__nombre_almacen")
    search_fields = ("orden__numero_orden", "codigo_articulo", "descripcion")


@admin.register(OrdenICGLog)
class OrdenICGLogAdmin(admin.ModelAdmin):
    list_display = ("orden", "fecha", "accion", "exito", "id_orden_icg")
    list_filter = ("exito", "fecha")
    search_fields = ("orden__numero_orden", "id_orden_icg", "mensaje")
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
    list_display = ("nombre", "nit", "email_contacto", "activo")
    search_fields = ("nombre", "nit")
    list_filter = ("activo",)
    inlines = [AsignacionMarcaVendedorInline, ProveedorUsuarioInline]
    # Opcional: agrupar campos
    fieldsets = (
        ("Identificación", {"fields": ("nombre", "nit")}),
        ("Contacto", {"fields": ("email_contacto",)}),
        ("Estado", {"fields": ("activo",)}),
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