from django.db import models
from django.contrib.auth import get_user_model
from auditlog.registry import auditlog

User = get_user_model()

class ReglaClasificacion(models.Model):
    CLASE_CHOICES = [
        ('A', 'Clase A'),
        ('B', 'Clase B'),
        ('C', 'Clase C'),
        ('D', 'Clase D'),
        ('E', 'Clase E'),
    ]

    clase = models.CharField(max_length=1, choices=CLASE_CHOICES)
    umbral_minimo = models.DecimalField(max_digits=5, decimal_places=2)
    umbral_maximo = models.DecimalField(max_digits=5, decimal_places=2)
    activa = models.BooleanField(default=True)
    orden = models.PositiveIntegerField(default=0, help_text="Prioridad de la regla")

    def __str__(self):
        return f"{self.clase}: {self.umbral_minimo} - {self.umbral_maximo} ({'Activa' if self.activa else 'Inactiva'})"

    class Meta:
        verbose_name = "Regla de Clasificación"
        verbose_name_plural = "Reglas de Clasificación"
        unique_together = ('clase', 'umbral_minimo', 'umbral_maximo')
        ordering = ['orden', 'umbral_minimo']
auditlog.register(ReglaClasificacion)

class ProcesoClasificacion(models.Model):
    fecha_inicio = models.DateTimeField(auto_now_add=True)
    usuario = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True
    )
    estado = models.CharField(
        max_length=20,
        choices=[
            ('extraccion', 'Extracción'),
            ('procesado', 'Procesado'),
            ('edicion', 'Edición'),
            ('confirmado', 'Confirmado'),
            ('actualizado', 'Actualizado en ICG')
        ],
        default='extraccion'
    )
    descripcion = models.TextField(blank=True)

    def __str__(self):
        return f"Proceso #{self.pk} - {self.fecha_inicio:%Y-%m-%d %H:%M} - {self.estado}"
    class Meta:
        verbose_name = "Proceso de Clasificación"
        verbose_name_plural = "Procesos de Clasificación"
        ordering = ['-fecha_inicio']
auditlog.register(ProcesoClasificacion)

# 1. Tabla de artículos extraídos, sin edición
class ArticuloClasificacionTemporal(models.Model):
    proceso = models.ForeignKey(
        ProcesoClasificacion,
        on_delete=models.CASCADE,
        related_name='articulos_temporales',
        blank=True, null=True
    )
    codigo = models.CharField(max_length=100)
    departamento = models.CharField(max_length=200, blank=True, null=True)
    seccion = models.CharField(max_length=200, blank=True, null=True)
    familia = models.CharField(max_length=200, blank=True, null=True)
    subfamilia = models.CharField(max_length=200, blank=True, null=True)
    marca = models.CharField(max_length=200, blank=True, null=True)
    descripcion = models.CharField(max_length=200,blank=True, null=True)
    descat = models.CharField(max_length=100, blank=True, null=True)
    tipo = models.CharField(max_length=100, blank=True, null=True)
    referencia = models.CharField(max_length=50, blank=True, null=True)
    clasificacion = models.CharField(max_length=100, blank=True, null=True)
    clasificacion2 = models.CharField(max_length=100, blank=True, null=True)
    clasificacion3 = models.CharField(max_length=100, blank=True, null=True)
    clasificacion5 = models.CharField(max_length=100, blank=True, null=True)
    unidades_compras = models.FloatField(blank=True, null=True)
    importe_compras = models.CharField(max_length=200, blank=True, null=True)
    unidades = models.FloatField(blank=True, null=True)
    coste = models.CharField(max_length=200, blank=True, null=True)
    beneficio = models.CharField(max_length=200, blank=True, null=True)
    importe = models.CharField(max_length=200, blank=True, null=True)
    porcentaje_sv = models.CharField(max_length=100, blank=True, null=True)
    stock_actual = models.FloatField(blank=True, null=True)
    valoracion_stock_actual = models.CharField(max_length=200, blank=True, null=True)
    almacen = models.CharField(max_length=100, blank=True, null=True)

    def __str__(self):
        return f"{self.codigo} - {self.descripcion}"

    class Meta:
        verbose_name = "Artículo Clasificación Temporal"
        verbose_name_plural = "Artículos Clasificación Temporal"
auditlog.register(ArticuloClasificacionTemporal)
# 2. Tabla de artículos en proceso, editables 
class ArticuloClasificacionProcesado(models.Model):
    """Tabla para artículos que han pasado por el proceso de clasificación y están en edición."""
    choises_clasificacion = (
        ('A', 'A'),
        ('B', 'B'),
        ('C', 'C'),
        ('E', 'E'),)
    proceso = models.ForeignKey(
        ProcesoClasificacion,
        on_delete=models.CASCADE,
        related_name='articulos_procesados'
    )
    seccion = models.CharField(max_length=100)
    codigo = models.CharField(max_length=20)
    descripcion = models.CharField(max_length=255, blank=True, null=True)
    referencia = models.CharField(max_length=30, blank=True, null=True)
    marca = models.CharField(max_length=100, blank=True, null=True)
    clasificacion_actual = models.CharField(max_length=5, blank=True, null=True)
    suma_importe = models.DecimalField(max_digits=12, decimal_places=2, blank=True, null=True)
    suma_unidades = models.IntegerField(blank=True, null=True)
    porcentaje_acumulado = models.DecimalField(max_digits=7, decimal_places=3, blank=True, null=True)
    nueva_clasificacion = models.CharField(max_length=5, blank=True, null=True, choices=choises_clasificacion)  # editable
    confirmado = models.BooleanField(default=False)  # Wizard step: confirmación
    almacen = models.CharField(max_length=100, blank=True, null=True)  # Almacén asociado
    importe_num = models.DecimalField(
        max_digits=25, decimal_places=2, blank=True, null=True,
        help_text="Valor de venta del artículo, si aplica",
        verbose_name="Importe Post"
    )

    fecha_creacion = models.DateTimeField(auto_now_add=True)
    fecha_actualizacion = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Artículo Clasificación Procesado"
        verbose_name_plural = "Artículos Clasificación Procesados"

    def __str__(self):
        return f"{self.seccion} - {self.codigo} - {self.descripcion}"
auditlog.register(ArticuloClasificacionProcesado)
# 3. Tabla final, con estado de acción y validación
class ArticuloClasificacionFinal(models.Model):
    proceso = models.ForeignKey(
        ProcesoClasificacion, on_delete=models.CASCADE, related_name='articulos_finales'
    )
    seccion = models.CharField(max_length=100)
    codigo = models.CharField(max_length=20)
    descripcion = models.CharField(max_length=255, blank=True, null=True)
    referencia = models.CharField(max_length=30, blank=True, null=True)
    marca = models.CharField(max_length=100, blank=True, null=True)
    clasificacion_actual = models.CharField(max_length=5, blank=True, null=True)
    nueva_clasificacion = models.CharField(max_length=5, blank=True, null=True)
    resultado_validacion = models.BooleanField()  # VERDADERO/FALSO
    almacen = models.CharField(max_length=100, blank=True, null=True) 

    estado_accion = models.CharField(
        max_length=30,
        choices=[("PENDIENTE", "Pendiente"), ("ACTUALIZADO", "Actualizado"), ("ERROR", "Error")],
        default="PENDIENTE"
    )
    mensaje_accion = models.TextField(blank=True, null=True)  # log o mensaje de error/success

    fecha_ejecucion = models.DateTimeField(auto_now_add=True)
    usuario = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True
    )

    class Meta:
        verbose_name = "Artículo Clasificación Final"
        verbose_name_plural = "Artículos Clasificación Final"

    def __str__(self):
        return f"{self.seccion} - {self.codigo} - {self.descripcion}"
auditlog.register(ArticuloClasificacionFinal)