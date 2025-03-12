from django.db import models

# Create your models here.
class SQLQuery(models.Model):
    nombre = models.CharField(max_length=255, unique=True)
    consulta = models.TextField(default='SELECT 1;')
    descripcion = models.TextField(blank=True, null=True)
    activa = models.BooleanField(default=True)
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    ultima_actualizacion = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.nombre

class Articulos(models.Model):
    id_articulo= models.CharField(max_length=50)
    store_id = models.CharField(max_length=20)
    ean = models.CharField(max_length=50, null=True, blank=True)
    name = models.CharField(max_length=255, null=True, blank=True)
    trademark = models.CharField(max_length=255, null=True, blank=True)
    description = models.TextField(null=True, blank=True)
    price = models.DecimalField(max_digits=10, decimal_places=2, default=0) 
    discount_price = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    stock = models.IntegerField()
    sale_type = models.CharField(max_length=5, default='U')
    is_available = models.BooleanField(default=False)
    departamento = models.CharField(max_length=255, null=True, blank=True)
    secciones = models.CharField(max_length=255, null=True, blank=True)
    familia = models.CharField(max_length=255, null=True, blank=True)
    subfamilia = models.CharField(max_length=255, null=True, blank=True)
    code = models.CharField(max_length=100, unique=True, null=True)  # Código único
    image = models.ImageField(upload_to='product_images/', null=True, blank=True)
    modificado = models.BooleanField(default=False)
    
    def __str__(self):
        return f"{self.name} ({self.code})"
    
    class Meta:
        verbose_name_plural = "Artículos"

class DescuentoDiario(models.Model):
    DIAS_SEMANA = [
        (0, "Lunes"),
        (1, "Martes"),
        (2, "Miércoles"),
        (3, "Jueves"),
        (4, "Viernes"),
        (5, "Sábado"),
        (6, "Domingo"),
    ]

    dia = models.IntegerField(choices=DIAS_SEMANA)
    departamento = models.CharField(max_length=200, blank=True, null=True)  
    secciones = models.CharField(max_length=200, blank=True, null=True)  
    familia = models.CharField(max_length=200, blank=True, null=True)
    porcentaje_descuento = models.FloatField(help_text="Ejemplo: 10 para 10% de descuento")

    def __str__(self):
        filtro = []
        if self.departamento:
            filtro.append(f"Depto: {self.departamento}")
        if self.secciones:
            filtro.append(f"Sección: {self.secciones}")
        if self.familia:
            filtro.append(f"Familia: {self.familia}")
        return f"{self.get_dia_display()} - {' / '.join(filtro)} ({self.porcentaje_descuento}%)"


class APILogRappi(models.Model):
    fecha = models.DateTimeField(auto_now_add=True)
    store_id = models.CharField(max_length=50)
    status_code = models.IntegerField()
    response_text = models.TextField()
    error_message = models.TextField(blank=True, null=True)

    def __str__(self):
        return f"{self.fecha} - Store {self.store_id} - Status {self.status_code}"