from django.contrib import admin
from django.utils.safestring import mark_safe
from .models import Employee, Equipment, Department, EquipmentCategory,CategoryOfIncidence, Binnacle

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
class EquipmentAdmin(admin.ModelAdmin):
    list_display = ('name', 'serial_number', 'status', 'category', 'assigned_to', 'photo_preview')
    list_filter = ('status', 'category', 'assigned_to')
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
class BinnacleAdmin(admin.ModelAdmin):
    list_display =('title','Category','created_at', 'status','user')
    list_filter =('status','Category',)
    search_fields = ('description',)
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
