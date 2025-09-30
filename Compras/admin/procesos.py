from django.contrib import admin
from django.urls import path, reverse
from django.utils.html import format_html
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect

# Importaciones locales
from ..models import (
    ProcesoClasificacion,
    ArticuloClasificacionProcesado,
    ArticuloClasificacionFinal
)
from ..tasks import cargar_proceso_clasificacion_task
from ..utils import procesar_clasificacion


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