from django.contrib import admin
from django.urls import path
from .models import (ProcesoClasificacion,
                      ArticuloClasificacionTemporal,
                      ArticuloClasificacionProcesado, 
                      ArticuloClasificacionFinal,
                      ReglaClasificacion)
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
    actions = ['exportar_excel']

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

    def exportar_excel(self, request, queryset):
        import openpyxl
        from django.http import HttpResponse
        from openpyxl.utils import get_column_letter
        from openpyxl.styles import Font

        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Clasificación Procesada"

        # Encabezados
        headers = [
            'Familia', 'Código', 'Descripción', 'Referencia', 'Marca',
            'Clasificación Actual', 'Nueva Clasificación', 'Almacén',
            'Importe', 'Unidades', 'Porcentaje Acumulado'
        ]
        ws.append(headers)
        for col_num, col_name in enumerate(headers, 1):
            ws.cell(row=1, column=col_num).font = Font(bold=True)

        # Filas
        for obj in queryset:
            ws.append([
                obj.seccion,  # Si el campo es realmente familia, cámbialo aquí
                obj.codigo,
                obj.descripcion,
                obj.referencia,
                obj.marca,
                obj.clasificacion_actual,
                obj.nueva_clasificacion,
                obj.almacen,
                obj.suma_importe,
                obj.suma_unidades,
                obj.porcentaje_acumulado,
            ])

        # Ajustar ancho de columnas
        for i, col in enumerate(headers, 1):
            ws.column_dimensions[get_column_letter(i)].width = 18

        response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        response['Content-Disposition'] = 'attachment; filename=clasificacion_procesada.xlsx'
        wb.save(response)
        return response
    exportar_excel.short_description = "Exportar a Excel"

