from django.contrib import admin
from django.urls import path
from .models import ProcesoClasificacion
from .views import ClasificacionWizard
from django import forms
from django.urls import reverse
from django.utils.html import format_html

class ProcesoClasificacionAdmin(admin.ModelAdmin):
    list_display = ['proceso_display', 'estado', 'fecha_inicio', 'lanzar_wizard']

    def proceso_display(self, obj):
        # Si el proceso está finalizado, resalta o separa con un distintivo
        if obj.estado == 'actualizado':
            return format_html(
                '<span style="padding:2px 10px; background:#eee; border-left:6px solid #19b23b; font-weight: bold; color: #19b23b;">{} (FINALIZADO)</span>',
                obj
            )
        return str(obj)
    proceso_display.short_description = 'Proceso'

    def lanzar_wizard(self, obj):
        # Si el proceso está finalizado, no muestra el botón
        if obj.estado == 'actualizado':
            return format_html('<span style="color:#aaa;">Completado</span>')
        else:
            url = reverse('admin:clasificacion-wizard', args=[obj.pk])
            return format_html(
                '<a class="button" style="background:#19b23b;color:#fff;padding:4px 8px;border-radius:4px;text-decoration:none;" href="{}">Procesar Clasificación</a>', url
            )
    lanzar_wizard.short_description = "Wizard"
    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path('clasificacion-wizard/<int:proceso_id>/', self.admin_site.admin_view(
                ClasificacionWizard.as_view([
                    ('step1', forms.Form),
                    ('step2', forms.Form),
                    ('step3', forms.Form),
                ])
            ), name='clasificacion-wizard'),
        ]
        return custom_urls + urls

admin.site.register(ProcesoClasificacion, ProcesoClasificacionAdmin)
