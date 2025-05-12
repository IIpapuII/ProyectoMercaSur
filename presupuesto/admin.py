from django.contrib import admin
from .models import ventapollos
# Register your models here.

@admin.register(ventapollos)
class VentapollosAdmin(admin.ModelAdmin):
    list_display = ('id', 'fecha', 'ubicacion', 'ValorVenta', 'create_date', 'update_date')
    list_filter = ('fecha', 'ubicacion')
    search_fields = ('fecha', 'ubicacion')
    ordering = ('-fecha',)
    date_hierarchy = 'fecha'
    list_per_page = 10