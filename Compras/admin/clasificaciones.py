from django.contrib import admin
from django.urls import path, reverse
from django.utils.html import format_html
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect
from django.http import HttpResponse
from django.forms import modelformset_factory
from io import BytesIO
from openpyxl import Workbook

# Importaciones locales
from ..models import (
    ReglaClasificacion,
    ArticuloClasificacionFinal, 
    ArticuloClasificacionProcesado,
    ArticuloClasificacionTemporal,
    ProcesoClasificacion
)
from ..tasks import actualizar_clasificaciones_en_icg
from ..utils import procesar_clasificacion
from presupuesto.utils import formato_dinero_colombiano


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
            actualizar_clasificaciones_en_icg.delay(proceso.pk)
            self.message_user(request, "Tarea encolada para actualizar artículos en ICG. Recargue para ver el resultado.", messages.INFO)
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
    
    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path('generar-clasificacion-final/', self.admin_site.admin_view(self.generar_clasificacion_final), name='generar_clasificacion_final'),
            path('exportar-excel/', self.admin_site.admin_view(self.exportar_excel), name='exportar_excel_procesado'),
        ]
        return custom_urls + urls
    
    def generar_clasificacion_final(self, request):
        proceso_id = request.GET.get('proceso__id__exact')
        if not proceso_id:
            messages.error(request, "No se proporcionó un ID de proceso.")
            return redirect("..")

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
            codigos_nuevos = set(ArticuloClasificacionTemporal.objects.filter(proceso=proceso, estado_nuevo='NUEVO').values_list('codigo', flat=True))
            for art in articulos:
                # Si el artículo es nuevo, resultado_validacion=False; si no, lógica original
                if art.codigo in codigos_nuevos and art.clasificacion_actual not in {"R", "T"}:
                    resultado_validacion = True
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

    def exportar_excel(self, request):
        """
        Exporta TODO el queryset filtrado actual (todas las páginas) como XLSX (Excel).
        Respeta búsqueda, filtros y orden del admin.
        """
        # Obtener queryset filtrado/ordenado actual
        cl = self.get_changelist_instance(request)
        qs = cl.queryset

        headers = [
            "Sección", "Código", "Descripción", "Referencia",
            "Marca", "Clasificación actual",
            "Suma importe", "Suma unidades",
            "Porcentaje acumulado", "Nueva clasificación", "Almacén",
        ]

        # Workbook en modo escritura eficiente
        wb = Workbook(write_only=True)
        ws = wb.create_sheet(title="Procesado")
        ws.append(headers)

        # Volcado en filas (iterador por chunks)
        for obj in qs.iterator(chunk_size=2000):
            ws.append([
                getattr(obj, "seccion", ""),
                getattr(obj, "codigo", ""),
                getattr(obj, "descripcion", ""),
                getattr(obj, "referencia", ""),
                getattr(obj, "marca", ""),
                getattr(obj, "clasificacion_actual", ""),
                getattr(obj, "suma_importe", ""),
                getattr(obj, "suma_unidades", ""),
                getattr(obj, "porcentaje_acumulado", ""),
                getattr(obj, "nueva_clasificacion", ""),
                getattr(obj, "almacen", ""),
            ])

        # Guardar a memoria y responder
        bio = BytesIO()
        wb.save(bio)
        bio.seek(0)

        proceso = request.GET.get("proceso__id__exact", "") or "all"
        resp = HttpResponse(
            bio.getvalue(),
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        resp['Content-Disposition'] = f'attachment; filename="articulos_procesados_proceso_{proceso}.xlsx"'
        return resp