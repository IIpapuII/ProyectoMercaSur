from import_export import resources, fields
from import_export.widgets import ForeignKeyWidget
from .models import Equipment, Binnacle, EquipmentCategory, Employee, Location, CategoryOfIncidence
from import_export.formats.base_formats import XLSX, XLS
from import_export.widgets import ForeignKeyWidget

class FullNameWidget(ForeignKeyWidget):
    def clean(self, value, row=None, *args, **kwargs):
        try:
            first_name, last_name = value.strip().split(' ', 1)
            return self.model.objects.get(first_name=first_name, last_name=last_name)
        except (ValueError, self.model.DoesNotExist):
            raise ValueError(f"Empleado no encontrado con nombre completo: {value}")

    def render(self, value, obj=None, **kwargs):  # Acepta kwargs adicionales
        return f"{value.first_name} {value.last_name}" if value else ''

class EquipmentResource(resources.ModelResource):
    category = fields.Field(
        column_name='category',
        attribute='category',
        widget=ForeignKeyWidget(EquipmentCategory, 'name')
    )
    assigned_to = fields.Field(
        column_name='assigned_to',
        attribute='assigned_to',
        widget=FullNameWidget(Employee)
    )
    location_equipment = fields.Field(
        column_name='location_equipment',
        attribute='location_equipment',
        widget=ForeignKeyWidget(Location, 'name')
    )
    

    class Meta:
        model = Equipment
        import_id_fields = ['serial_number']
        fields = (
            'serial_number',
            'name',
            'model_equipmet',
            'activo_fijo',
            'category',
            'purchase_date',
            'status',
            'assigned_to',
            'location_equipment',
            'notes',
            'date_create',
        )
        skip_unchanged = True
        report_skipped = True
        formats = ['xlsx', 'xls']


class BinnacleResource(resources.ModelResource):
    Category = fields.Field(
        column_name='Category',
        attribute='Category',
        widget=ForeignKeyWidget(CategoryOfIncidence, 'name_category')
    )
    equipment_service = fields.Field(
        column_name='equipment_service',
        attribute='equipment_service',
        widget=ForeignKeyWidget(Equipment, 'serial_number')
    )
    employee_service = fields.Field(
        column_name='employee_service',
        attribute='employee_service',
        widget=FullNameWidget(Employee)
    )
    location = fields.Field(
        column_name='location',
        attribute='location',
        widget=ForeignKeyWidget(Location, 'name')
    )

    class Meta:
        model = Binnacle
        import_id_fields = ['title', 'created_at']
        fields = (
            'title',
            'Category',
            'equipment_service',
            'employee_service',
            'location',
            'description',
            'status',
            'created_at',
            'status_changed_at',
        )
        skip_unchanged = True
        report_skipped = True
        formats = ['xlsx', 'xls']