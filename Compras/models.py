from django.db import models
from django.contrib.auth import get_user_model

User = get_user_model()

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


# 1. Tabla de artículos extraídos, sin edición
class ArticuloClasificacionTemporal(models.Model):
    proceso = models.ForeignKey(
        ProcesoClasificacion,
        on_delete=models.CASCADE,
        related_name='articulos_temporales',
        blank=True, null=True
    )
    codigo = models.CharField(max_length=100)
    departamento = models.CharField(max_length=200)
    seccion = models.CharField(max_length=200, blank=True, null=True)
    familia = models.CharField(max_length=200, blank=True, null=True)
    subfamilia = models.CharField(max_length=200, blank=True, null=True)
    marca = models.CharField(max_length=200, blank=True, null=True)
    descripcion = models.CharField(max_length=200)
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

    def __str__(self):
        return f"{self.codigo} - {self.descripcion}"

    class Meta:
        verbose_name = "Artículo Clasificación Temporal"
        verbose_name_plural = "Artículos Clasificación Temporal"

# 2. Tabla de artículos en proceso, editables y con campos para el wizard
class ArticuloClasificacionProcesado(models.Model):
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
    nueva_clasificacion = models.CharField(max_length=5, blank=True, null=True)  # editable
    confirmado = models.BooleanField(default=False)  # Wizard step: confirmación

    fecha_creacion = models.DateTimeField(auto_now_add=True)
    fecha_actualizacion = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Artículo Clasificación Procesado"
        verbose_name_plural = "Artículos Clasificación Procesados"

    def __str__(self):
        return f"{self.seccion} - {self.codigo} - {self.descripcion}"

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
