from django.contrib import admin
from .models import RegistroCliente
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