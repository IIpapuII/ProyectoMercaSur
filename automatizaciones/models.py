from django.db import models
from django.utils.timezone import now

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
    code = models.CharField(max_length=100, null=True, unique=True)  # Código único
    image = models.ImageField(upload_to='product_images/', null=True, blank=True)
    modificado = models.BooleanField(default=False)
    tarifa = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    is_featured = models.BooleanField(default=False)
    
    def __str__(self):
        return f"{self.name} ({self.code})"
    
    class Meta:
        verbose_name_plural = "Artículos"

from django.db import models
from datetime import date

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

    dia = models.IntegerField(choices=DIAS_SEMANA, blank=True, null=True)  # Permitir NULL para descuentos siempre activos
    departamento = models.CharField(max_length=200, blank=True, null=True)
    secciones = models.CharField(max_length=200, blank=True, null=True)
    familia = models.CharField(max_length=200, blank=True, null=True)
    Trademark = models.CharField(max_length=200, blank=True, null=True, verbose_name="Marca")
    ean = models.CharField(max_length=50, blank=True, null=True, unique=True)  # Para descuentos por producto específico
    porcentaje_descuento = models.FloatField(help_text="Ejemplo: 10 para 10% de descuento")
    fecha_inicio = models.DateField(blank=True, null=True, help_text="Fecha desde la cual se aplica el descuento")
    fecha_fin = models.DateField(blank=True, null=True, help_text="Fecha hasta la cual es válido el descuento")
    destacado = models.BooleanField(default=False)
    maximo_venta = models.PositiveIntegerField(default=0, help_text="Cantidad máxima de unidades con venta por cliente")
    activo = models.BooleanField(default=True, help_text="Indica si el descuento está activo o no")

    def esta_vigente(self):
        """Devuelve True si el descuento está dentro del rango de fechas."""
        hoy = date.today()
        if self.fecha_inicio and hoy < self.fecha_inicio:
            return False
        if self.fecha_fin and hoy > self.fecha_fin:
            return False
        return True

    def __str__(self):
        filtros = []
        if self.ean:
            filtros.append(f"EAN: {self.ean}")
        if self.departamento:
            filtros.append(f"Depto: {self.departamento}")
        if self.secciones:
            filtros.append(f"Sección: {self.secciones}")
        if self.familia:
            filtros.append(f"Familia: {self.familia}")

        fecha_info = f"({self.fecha_inicio} - {self.fecha_fin})" if self.fecha_inicio or self.fecha_fin else "(Siempre activo)"
        return f"{self.get_dia_display() if self.dia is not None else 'Todos los días'} - {' / '.join(filtros)} {fecha_info} ({self.porcentaje_descuento}%)"



class APILogRappi(models.Model):
    fecha = models.DateTimeField(auto_now_add=True)
    store_id = models.CharField(max_length=50)
    status_code = models.IntegerField()
    response_text = models.TextField()
    error_message = models.TextField(blank=True, null=True)

    def __str__(self):
        return f"{self.fecha} - Store {self.store_id} - Status {self.status_code}"


class Presentation(models.Model):
    product = models.OneToOneField("Product", on_delete=models.CASCADE, related_name="presentation_info")
    quantity = models.PositiveIntegerField()
    unit_type = models.CharField(max_length=10)

class SellType(models.Model):
    product = models.OneToOneField("Product", on_delete=models.CASCADE, related_name="sell_type_info")
    type = models.CharField(max_length=5)
    min_quantity = models.PositiveIntegerField()
    max_quantity = models.PositiveIntegerField()
    step_quantity = models.PositiveIntegerField()

class Product(models.Model):
    category_id = models.IntegerField()
    name = models.CharField(max_length=255)
    description = models.TextField()
    has_variation = models.BooleanField(default=False)
    presentation = models.OneToOneField(Presentation, on_delete=models.CASCADE, related_name="product_presentation")
    sell_type = models.OneToOneField(SellType, on_delete=models.CASCADE, related_name="product_sell_type")

class ProductSKU(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="skus")
    sku = models.CharField(max_length=50, unique=True)
    ean = models.BigIntegerField(unique=True)

class ProductImage(models.Model):
    product_sku = models.ForeignKey(ProductSKU, on_delete=models.CASCADE, related_name="images")
    path = models.URLField()
    position = models.PositiveIntegerField()

class ProductAttribute(models.Model):
    product_sku = models.OneToOneField(ProductSKU, on_delete=models.CASCADE, related_name="attributes")
    color_alt = models.CharField(max_length=50, blank=True, null=True)


class EnvioLog(models.Model):
    STATUS_CHOICES = [
        ("success", "Éxito"),
        ("error", "Error"),
    ]

    timestamp = models.DateTimeField(default=now)  # Fecha y hora del intento
    archivo = models.CharField(max_length=255)  # Nombre o ruta del archivo enviado
    status = models.CharField(max_length=10, choices=STATUS_CHOICES)  # Estado del envío
    status_code = models.IntegerField(null=True, blank=True)  # Código de estado HTTP
    response_text = models.TextField(blank=True)  # Respuesta de la API o mensaje de error

    def __str__(self):
        return f"{self.timestamp} - {self.archivo} - {self.status} ({self.status_code})"