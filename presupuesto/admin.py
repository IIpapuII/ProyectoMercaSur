from django.contrib import admin
from .models import VentaDiariaReal, ventapollos,Sede, CategoriaVenta, PorcentajeDiarioConfig, PresupuestoMensualCategoria, PresupuestoDiarioCategoria

from decimal import Decimal

@admin.register(Sede)
class SedeAdmin(admin.ModelAdmin):
    list_display = ('nombre',)
    search_fields = ('nombre',)

@admin.register(CategoriaVenta)
class CategoriaVentaAdmin(admin.ModelAdmin):
    list_display = ('nombre',)
    search_fields = ('nombre',)

@admin.register(PorcentajeDiarioConfig)
class PorcentajeDiarioConfigAdmin(admin.ModelAdmin):
    list_display = ('categoria', 'get_dia_semana_display', 'porcentaje')
    list_filter = ('categoria__nombre',) # Filtrar por nombre de categoría
    ordering = ('categoria__nombre', 'dia_semana')
    list_editable = ('porcentaje',) # Permitir editar porcentaje en la lista
    list_per_page = 49 # Mostrar 7 semanas por página

    @admin.display(description='Día de la Semana', ordering='dia_semana')
    def get_dia_semana_display(self, obj):
        return obj.get_dia_semana_display()

    # Acción para verificar que los porcentajes suman 100 para las categorías seleccionadas
    def check_percentage_sum(self, request, queryset):
        categories_checked = {}
        for config in queryset.select_related('categoria'):
            cat_name = config.categoria.nombre
            if cat_name not in categories_checked:
                # Obtener todos los porcentajes para esta categoría
                all_pcts = PorcentajeDiarioConfig.objects.filter(categoria=config.categoria)
                total = sum(p.porcentaje for p in all_pcts)
                count = all_pcts.count()
                if count != 7 or total != Decimal('100.00'):
                    self.message_user(
                        request,
                        f"¡Error en '{cat_name}'! Se encontraron {count} días y la suma es {total}. Debe ser 7 días y sumar 100.",
                        level='ERROR'
                    )
                else:
                     categories_checked[cat_name] = total # Marcar como verificada OK
            elif cat_name in categories_checked and categories_checked[cat_name]!=Decimal('100.00'):
                # Si ya se marcó con error, no repetir OK
                pass
            elif cat_name not in categories_checked:
                 # Solo marcamos OK si no hubo error previo
                 categories_checked[cat_name] = Decimal('100.00')


        # Mensaje general si algunas verificadas estaban OK
        ok_cats = [name for name, total in categories_checked.items() if total == Decimal('100.00')]
        if ok_cats:
             self.message_user(request, f"Verificación completada. Categorías OK: {', '.join(ok_cats)}.", level='INFO')


    check_percentage_sum.short_description = "Verificar suma de porcentajes (100)"
    actions = [check_percentage_sum]


@admin.register(PresupuestoMensualCategoria)
class PresupuestoMensualCategoriaAdmin(admin.ModelAdmin):
    list_display = ('sede', 'categoria', 'anio', 'mes', 'presupuesto_total_categoria')
    list_filter = ('sede__nombre', 'categoria__nombre', 'anio', 'mes')
    search_fields = ('sede__nombre', 'categoria__nombre')
    ordering = ('sede__nombre', 'anio', 'mes', 'categoria__nombre')
    list_per_page = 25

@admin.register(PresupuestoDiarioCategoria)
class PresupuestoDiarioCategoriaAdmin(admin.ModelAdmin):
    list_display = (
        'fecha', 'get_sede', 'get_categoria', 'dia_semana_nombre',
        'porcentaje_dia_especifico', 'presupuesto_calculado'
    )
    list_filter = (
        'presupuesto_mensual__sede__nombre',
        'presupuesto_mensual__categoria__nombre',
        'fecha' # Podría ser lento con muchos datos, considerar DateHierarchy
    )
    search_fields = (
        'presupuesto_mensual__sede__nombre',
        'presupuesto_mensual__categoria__nombre',
        'fecha'
    )
    ordering = ('-fecha', 'presupuesto_mensual__sede__nombre', 'presupuesto_mensual__categoria__nombre')
    list_per_page = 30
    date_hierarchy = 'fecha' # Para navegación por fechas

    @admin.display(description='Sede', ordering='presupuesto_mensual__sede__nombre')
    def get_sede(self, obj):
        return obj.presupuesto_mensual.sede.nombre

    @admin.display(description='Categoría', ordering='presupuesto_mensual__categoria__nombre')
    def get_categoria(self, obj):
        return obj.presupuesto_mensual.categoria.nombre
@admin.register(ventapollos)
class VentapollosAdmin(admin.ModelAdmin):
    list_display = ('id', 'fecha', 'ubicacion', 'ValorVenta', 'create_date', 'update_date')
    list_filter = ('fecha', 'ubicacion')
    search_fields = ('fecha', 'ubicacion')
    ordering = ('-fecha',)
    date_hierarchy = 'fecha'
    list_per_page = 10

@admin.register(VentaDiariaReal)
class VentaDiariaRealAdmin(admin.ModelAdmin):
    list_display = ('fecha', 'get_sede_nombre', 'get_categoria_nombre', 'venta_real_formatted')
    list_filter = ('fecha', 'sede__nombre', 'categoria__nombre')
    search_fields = ('sede__nombre', 'categoria__nombre', 'fecha')
    date_hierarchy = 'fecha'
    ordering = ('-fecha', 'sede__nombre', 'categoria__nombre')
    list_per_page = 25

    @admin.display(description='Sede', ordering='sede__nombre')
    def get_sede_nombre(self, obj):
        return obj.sede.nombre

    @admin.display(description='Categoría', ordering='categoria__nombre')
    def get_categoria_nombre(self, obj):
        return obj.categoria.nombre

    @admin.display(description='Venta Real ($)', ordering='venta_real')
    def venta_real_formatted(self, obj):
        return f"${obj.venta_real:,.2f}"
