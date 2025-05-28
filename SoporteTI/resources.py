from import_export import resources, fields
from import_export.widgets import ForeignKeyWidget
from .models import Equipment, Binnacle, EquipmentCategory, Employee, Location, CategoryOfIncidence
from import_export.formats.base_formats import XLSX, XLS

class EquipmentResource(resources.ModelResource):
    category = fields.Field(
        column_name='category',
        attribute='category',
        widget=ForeignKeyWidget(EquipmentCategory, 'name')
    )
    assigned_to = fields.Field(
        column_name='assigned_to',
        attribute='assigned_to',
        widget=ForeignKeyWidget(Employee, 'email')
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
            'warranty_expiration_date',
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
        widget=ForeignKeyWidget(Employee, 'email')
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