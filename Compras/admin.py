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
            count, errores = actualizar_clasificaciones_en_icg(proceso)
            if errores:
                msg = f"Se actualizaron {count} artículos, pero hubo errores:<br>{errores}"
                self.message_user(request, format_html(msg), messages.WARNING)
                
            else:
                self.message_user(request, f"Se actualizaron {count} artículos correctamente en ICG.", messages.SUCCESS)
                proceso.estado = 'actualizado'
                proceso.save(update_fields=['estado'])
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
        'suma_importe', 'suma_unidades',
        'porcentaje_acumulado', 'nueva_clasificacion', 'almacen'
    )
    list_editable = ('nueva_clasificacion',)
    list_filter = (
        'seccion', 'marca', 'clasificacion_actual', 'almacen'
    )
    search_fields = ('codigo', 'descripcion', 'referencia')
    ordering = ('seccion', '-suma_importe', 'almacen')
    change_list_template = "admin/Compras/articuloclasificacionprocesado/change_list.html"

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
        from .utils import procesar_clasificacion  # si lo estás usando

        # Obtener el proceso
        proceso = get_object_or_404(ProcesoClasificacion, pk=proceso_id)

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
        cargar_proceso_clasificacion_task(user_id=request.user.id)
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
        if obj.estado != 'actualizado':
            url = reverse(
            'admin:compras_procesoclasificacion_procesar',
            args=[obj.pk]
        )
            return format_html(
                '<a class="button" style="background:#19b23b;color:#fff;padding:4px 8px;border-radius:4px;text-decoration:none;" href="{}">Procesar Clasificación</a>', url
            )
        return format_html('<span style="color:#aaa;">Completado</span>')
    lanzar_wizard.short_description = 'Acción'

    def get_urls(self):
        urls = super().get_urls()
        custom = [
            path(
                '<int:proceso_id>/procesar/',
                self.admin_site.admin_view(self.procesar_view),
                name='compras_procesoclasificacion_procesar'
            )
        ]
        return custom + urls
    
    def procesar_view(self, request, proceso_id, *args, **kwargs):
        proceso = get_object_or_404(ProcesoClasificacion, pk=proceso_id)

        # 1) Poblar ArticuloClasificacionProcesado...
        if proceso.estado == 'procesado':
            messages.warning(request, f"La clasificación esta en el estado de {proceso.estado} .")
        else:
            procesar_clasificacion(proceso)
            messages.success(request, "Clasificación procesada correctamente.")

        # 2) Construir dinámicamente la URL del changelist de ArticuloClasificacionProcesado
        opts = ArticuloClasificacionProcesado._meta
        changelist_url = reverse(
            'admin:%s_%s_changelist' % (opts.app_label, opts.model_name)
        )
        # Añadimos un filtro para que sólo muestre los de este proceso
        changelist_url += f'?proceso__id__exact={proceso.pk}'
        if proceso.estado == 'procesado':
            return redirect(changelist_url)
        # 3) Redirigir
        return redirect(changelist_url)

