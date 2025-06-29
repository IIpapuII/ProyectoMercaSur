from django.db import models
from django.contrib.auth.models import User
from django_ckeditor_5.fields import CKEditor5Field
from datetime import datetime

class Department(models.Model):
    name = models.CharField(max_length=100, unique=True, verbose_name="Departamento")
    description = models.TextField(blank=True, null=True, verbose_name="Descripción")

    def __str__(self):
        return self.name
    class Meta:
      verbose_name = "Departamento"

class Location(models.Model):
    name = models.CharField(max_length=100, unique=True, verbose_name="Ubicación")
    description = models.TextField(blank=True, null=True, verbose_name="Descripción")

    def __str__(self):
        return self.name
    class Meta:
      verbose_name = "Ubicación"
      verbose_name_plural = "Ubicaciones"

class Employee(models.Model):
    first_name = models.CharField(max_length=50, verbose_name="Nombre")
    last_name = models.CharField(max_length=50, verbose_name="Apellido")
    email = models.EmailField(verbose_name="Correo electrónico")
    phone = models.CharField(max_length=20, verbose_name="Teléfono", blank=True, null=True)
    department = models.ForeignKey(Department, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Departamento")

    def __str__(self):
        return f"{self.first_name} {self.last_name}"
    
    class Meta:
      verbose_name = "Colaborador"
      verbose_name_plural = "Colaboradores"

class EquipmentCategory(models.Model):
    name = models.CharField(max_length=100, unique=True, verbose_name="Categoría")
    description = models.TextField(blank=True, null=True, verbose_name="Descripción")

    def __str__(self):
        return self.name
    class Meta:
        verbose_name = "Categorias Equipos"
        verbose_name_plural = "Categorias Equipos"

class Equipment(models.Model):
    class EquipmentStatus(models.TextChoices):
        AVAILABLE = 'Available', 'Disponible'
        IN_USE = 'In Use', 'En uso'
        MAINTENANCE = 'Maintenance', 'Mantenimiento'
        RETIRED = 'Retirado', 'Retirado'
        BUENO = 'Bueno', 'Bueno Estado'
        MAL_ESTADO = 'Mal Estado', 'Mal Estado'
        NUEVO = 'Nuevo', 'Nuevo'
        BAJA = 'Baja', 'Baja'

    serial_number = models.CharField(max_length=100, unique=True, verbose_name="Número de serie")
    name = models.CharField(max_length=100, verbose_name="Nombre del equipo")
    model_equipmet = models.CharField(max_length=100, verbose_name="Model del Equipo", blank= True, null= True)
    activo_fijo = models.CharField(max_length=100, verbose_name="Activo Fijo", blank= True, null= True)
    category = models.ForeignKey(EquipmentCategory, on_delete=models.SET_NULL, null=True, verbose_name="Categoría")
    purchase_date = models.DateField(verbose_name="Fecha de compra")
    status = models.CharField(
        max_length=20,
        choices=EquipmentStatus.choices,
        default=EquipmentStatus.AVAILABLE,
        verbose_name="Estado"
    )
    assigned_to = models.ForeignKey(Employee, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Asignado a")
    location_equipment = models.ForeignKey(Location, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Ubicación")
    notes = models.TextField(blank=True, null=True, verbose_name="Notas")
    photo = models.ImageField(upload_to='equipment_photos/', blank=True, null=True, verbose_name="Evidencia fotográfica")
    date_create = models.DateTimeField(verbose_name='Fecha de Creación', auto_now_add=True, null= True , blank=True)


    def __str__(self):
        return f"{self.name} ({self.serial_number})"
    class Meta:
        verbose_name = "Equipos"
        verbose_name_plural = "Equipos"


class CategoryOfIncidence(models.Model):
    name_category = models.CharField(max_length = 100, verbose_name= 'Nombre Categoria')

    def __str__(self):
        return self.name_category

    class Meta:
        verbose_name = 'Categoria de Insidencia'
        verbose_name_plural = 'Categorias de Insidencia'
    
class Binnacle(models.Model):
    STATUS_CHOICES = [
        ('Pendiente', 'Pendiente'),
        ('En Proceso', 'En Proceso'),
        ('Resuelto', 'Resuelto'),
        ('Cancelado', 'Cancelado'),
    ]
    title = models.CharField(max_length = 200, verbose_name= 'Titulo')
    Category = models.ForeignKey(CategoryOfIncidence, on_delete=models.CASCADE, verbose_name='Categoria de Insidencia' )
    equipment_service_category = models.ForeignKey(EquipmentCategory, on_delete=models.CASCADE, verbose_name ='Equipo Categoria', blank = True, null= True)
    employee_service = models.ForeignKey(Employee, on_delete=models.CASCADE, verbose_name='Empleado de solicitud', blank = True, null= True)
    location = models.ForeignKey(Location, on_delete=models.CASCADE, verbose_name='Ubicación', blank = True, null= True)
    fechaSolicitud = models.DateTimeField(verbose_name="Fecha de Solicitud", null=True, blank=True)
    description = CKEditor5Field(verbose_name="Descripción", config_name="default")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, verbose_name="Estado" , default = STATUS_CHOICES[0])
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Fecha de creación")
    status_changed_at = models.DateTimeField(null=True, blank=True, verbose_name="Fecha de cambio de estado")
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="binnacles", verbose_name="Usuario", blank = True, null = True)

    def save(self, *args, **kwargs):
        if (self.status == 'Resuelto' or self.status == 'Cancelado') and not self.status_changed_at:
            self.status_changed_at = datetime.now()
        super().save(*args, **kwargs)

    def __str__(self):
        return self.title
    
    class Meta:
        verbose_name = 'Bitacora 202'
        verbose_name_plural = 'Bitacoras 202'

class BinnacleDasboardProxy(Binnacle):
    class Meta:
        proxy = True
        verbose_name = 'Bitacora 202 Dashboard'
        verbose_name_plural = 'Bitacoras 202 Dashboard'
    
    def __str__(self):
        return f"Dashboard: {self.title}"
    
    def get_status_display(self):
        return self.get_status_display()  # Utiliza el método original para obtener la representación del estado