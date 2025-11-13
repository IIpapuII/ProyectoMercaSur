from django.contrib import admin
from django.urls import path
from django.http import JsonResponse
from django.contrib import messages
from django.shortcuts import redirect

# Importaciones locales
from ..models import (
    Proveedor,
    Marca,
    VendedorPerfil,
    AsignacionMarcaVendedor,
    ProveedorUsuario
)
from ..services.Actualizar_proveedores import actualizar_proveedores_desde_icg


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
    change_list_template = "admin/compras/proveedor/change_list.html"
    list_display = ("nombre","presupuesto_mensual", "nit", "email_contacto", "activo")
    search_fields = ("nombre", "nit")
    list_filter = ("activo",)
    inlines = [AsignacionMarcaVendedorInline, ProveedorUsuarioInline]
    # Opcional: agrupar campos
    fieldsets = (
        ("Identificación", {"fields": ("nombre", "nit", "presupuesto_mensual", "activo")}),
        ("Contacto", {"fields": ("email_contacto",)}),
    )
    
    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path('actualizar-proveedores/', self.admin_site.admin_view(self.actualizar_proveedores_view), name='compras_proveedor_actualizar'),
        ]
        return custom_urls + urls
    
    def actualizar_proveedores_view(self, request):
        """Vista para actualizar proveedores desde ICG"""
        if request.method == 'POST':
            resultado = actualizar_proveedores_desde_icg()
            
            if resultado['success']:
                messages.success(request, resultado['mensaje'])
            else:
                messages.error(request, resultado['mensaje'])
            
            return redirect('admin:Compras_proveedor_changelist')
        
        return JsonResponse({'error': 'Método no permitido'}, status=405)


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