from django.contrib import admin
from django.utils.safestring import mark_safe
from .models import Employee, Equipment, Department, EquipmentCategory,CategoryOfIncidence, Binnacle, Location
from .resources import EquipmentResource, BinnacleResource
from import_export.admin import ImportExportModelAdmin

@admin.register(Location)
class LocationAdmin(admin.ModelAdmin):
    list_display = ('name', 'description')
    search_fields = ('name',)
    list_per_page = 20

@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    list_display = ('name', 'description')
    search_fields = ('name',)
    list_per_page = 20

@admin.register(EquipmentCategory)
class EquipmentCategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'description')
    search_fields = ('name',)
    list_per_page = 20


@admin.register(Employee)
class EmployeeAdmin(admin.ModelAdmin):
    list_display = ('first_name', 'last_name', 'email', 'phone', 'department')
    list_per_page = 20

@admin.register(Equipment)
class EquipmentAdmin(ImportExportModelAdmin):
    resource_class = EquipmentResource
    list_display = ('location_equipment','name','model_equipmet','serial_number','activo_fijo', 'status', 'category', 'assigned_to', 'photo_preview')
    list_filter = ('status', 'category', 'assigned_to', 'location_equipment')
    search_fields = ('name', 'serial_number')
    list_per_page = 20
    
    # Mostrar una vista previa de la foto en el panel de administración
    def photo_preview(self, obj):
        if obj.photo:
            return mark_safe(f'<img src="{obj.photo.url}" style="max-height: 50px;"/>')
        return "Sin imagen"
    photo_preview.short_description = "Vista previa de la foto"

@admin.register(CategoryOfIncidence)
class CategoryOfIncidenceAdmin(admin.ModelAdmin):
    list_display = ('name_category',)

@admin.register(Binnacle)
class BinnacleAdmin(ImportExportModelAdmin):
    resource_class = BinnacleResource
    list_display =('title','Category','location','employee_service','created_at', 'status','user')
    list_filter =('status','Category', 'equipment_service', 'employee_service', 'location')
    search_fields = ('description','title',)
    ordering = ('-created_at',)
    list_per_page = 40
    
    def get_exclude(self, request, obj=None):
        
        if not request.user.is_superuser:
            return ('status_changed_at', 'user')
        return super().get_exclude(request, obj)

    def get_queryset(self, request):
        """Filtra los elementos para mostrar solo los de este usuario"""
        queryset = super().get_queryset(request)
        if not request.user.is_superuser:
            queryset = queryset.filter(user=request.user, status__in=['Pendiente', 'En Proceso'])
        return queryset

    def save_model(self, request, obj, form, change):
        """Asocia el usuario al momento de crear o editar"""
        if not obj.user:
            obj.user = request.user
        obj.save()
