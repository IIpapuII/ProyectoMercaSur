from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
from decimal import Decimal

# Sede y CategoriaVenta permanecen igual que en la respuesta anterior
class Sede(models.Model):
    nombre = models.CharField(max_length=100, unique=True)
    def __str__(self): return self.nombre

class CategoriaVenta(models.Model):
    nombre = models.CharField(max_length=100, unique=True) # Fruver, Carnes, Panadería, "Total Sede"
    def __str__(self): return self.nombre

class Eventos(models.Model):
    nombre = models.CharField(max_length=100, unique=True)
    def __str__(self): return self.nombre

class PorcentajeDiarioConfig(models.Model):
    """
    Almacena el conjunto de porcentajes de distribución diaria para una categoría.
    Cada categoría (Fruver, Carnes, Total Sede, etc.) tendrá 7 registros aquí.
    """
    sede = models.ForeignKey(Sede, on_delete=models.CASCADE, related_name="config_porcentajes", null=True)
    categoria = models.ForeignKey(CategoriaVenta, on_delete=models.CASCADE, related_name="config_porcentajes")
    DIA_SEMANA_CHOICES = [
        (0, 'Lunes'), (1, 'Martes'), (2, 'Miércoles'),
        (3, 'Jueves'), (4, 'Viernes'), (5, 'Sábado'), (6, 'Domingo')
    ]
    dia_semana = models.IntegerField(choices=DIA_SEMANA_CHOICES) # 0=Lunes, 6=Domingo
    porcentaje = models.DecimalField(
        max_digits=5, decimal_places=2,
        validators=[MinValueValidator(Decimal('0.00')), MaxValueValidator(Decimal('100.00'))],
        help_text="Porcentaje para este día (ej: 18.50 para 18.50%)"
    )

    class Meta:
        unique_together = ('sede','categoria', 'dia_semana',) # Solo un porcentaje por día para cada categoría
        ordering = ['sede','categoria', 'dia_semana']
        verbose_name = "Configuración de Porcentaje Diario"
        verbose_name_plural = "Configuraciones de Porcentajes Diarios"

    def __str__(self):
        return f"{self.categoria.nombre} - {self.get_dia_semana_display()}: {self.porcentaje}%"

# PresupuestoMensualCategoria permanece mayormente igual, pero ahora es más crucial
# que CategoriaVenta incluya una entrada para "Total Sede" si esta tiene su propio presupuesto.
class PresupuestoMensualCategoria(models.Model):
    sede = models.ForeignKey(Sede, on_delete=models.CASCADE)
    categoria = models.ForeignKey(CategoriaVenta, on_delete=models.CASCADE) # Incluye "Total Sede"
    anio = models.IntegerField()
    mes = models.IntegerField()
    presupuesto_total_categoria = models.DecimalField(
        max_digits=15, decimal_places=2, default=Decimal('0.00')
    )
    # ... (Meta y __str__ como antes)
    class Meta:
        unique_together = ('sede', 'categoria', 'anio', 'mes')
        verbose_name = "Presupuesto Mensual por Categoría"
        verbose_name_plural = "Presupuestos Mensuales por Categoría"
    def __str__(self):
        return f"{self.sede.nombre} - {self.categoria.nombre} - {self.mes}/{self.anio} - ${self.presupuesto_total_categoria:,.2f}"


# PresupuestoDiarioCategoria también es similar, pero el 'porcentaje_aplicado'
# ahora vendrá del PorcentajeDiarioConfig de esa categoría para ese día.
class PresupuestoDiarioCategoria(models.Model):
    presupuesto_mensual = models.ForeignKey(
        PresupuestoMensualCategoria, related_name='dias_calculados', on_delete=models.CASCADE
    )
    fecha = models.DateField()
    dia_semana_nombre = models.CharField(max_length=10) # Lunes, Martes... (nombre del día)
    porcentaje_dia_especifico = models.DecimalField(
        max_digits=5, decimal_places=2,
        help_text="El porcentaje específico de esta categoría para este día de la semana"
    )
    presupuesto_calculado = models.DecimalField(max_digits=15, decimal_places=2)
    # ... (Meta y __str__ como antes)
    class Meta:
        unique_together = ('presupuesto_mensual', 'fecha')
        ordering = ['fecha']
        verbose_name = "Presupuesto Diario por Categoría"
        verbose_name_plural = "Presupuestos Diarios por Categoría"
    def __str__(self):
        return f"{self.presupuesto_mensual.sede.nombre} - {self.presupuesto_mensual.categoria.nombre} - {self.fecha} ({self.dia_semana_nombre}) - Pct:{self.porcentaje_dia_especifico} - Val:${self.presupuesto_calculado:,.2f}"
    
class VentaDiariaReal(models.Model):
    """Almacena la venta real para una categoría específica, en una sede, en una fecha."""
    sede = models.ForeignKey(Sede, on_delete=models.CASCADE, verbose_name="Sede")
    categoria = models.ForeignKey(CategoriaVenta, on_delete=models.CASCADE, verbose_name="Categoría")
    fecha = models.DateField(verbose_name="Fecha de la Venta")
    venta_real = models.DecimalField(
        max_digits=15, decimal_places=2,
        default=Decimal('0.00'),
        verbose_name="Venta Real ($)"
    )
    margen_sin_post_pct = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal('0.0'),
        verbose_name="% Margen Sin POS"
    )
    margen_con_post_pct = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal('0.0'),
        verbose_name="% Margen Con POS"
    )
    # Campo opcional para notas o comentarios sobre la venta de ese día
    # notas = models.TextField(blank=True, null=True, verbose_name="Notas Adicionales")
    Eventos = models.ForeignKey(
        Eventos, on_delete=models.CASCADE, related_name='ventas_diarias', null=True, blank=True,
        verbose_name="Evento Asociado"
    )

    class Meta:
        unique_together = ('sede', 'categoria', 'fecha') # Evita registros duplicados
        ordering = ['fecha', 'sede', 'categoria']
        verbose_name = "Venta Diaria Real"
        verbose_name_plural = "Ventas Diarias Reales"

    def __str__(self):
        return f"{self.fecha} - {self.sede.nombre} - {self.categoria.nombre} - Venta: ${self.venta_real:,.2f}"

class ventapollos(models.Model):
    choiseUbicacion = (
        ('CALDAS', 'CALDAS'),
        ('CENTRO', 'CENTRO'),
    )
    id = models.AutoField(primary_key=True)
    fecha = models.DateField(verbose_name='Fecha')
    ubicacion = models.CharField(max_length=100, choices=choiseUbicacion, verbose_name='Ubicación')
    ValorVenta = models.DecimalField(max_digits=10, decimal_places=2, verbose_name='Valor de Venta')
    create_date = models.DateTimeField(auto_now_add=True)
    update_date = models.DateTimeField(auto_now=True)
    class Meta:
        verbose_name = 'Concesión de Pollos'
        verbose_name_plural = 'Consesión de Pollos'
        ordering = ['-fecha']

    def save(self, *args, **kwargs):
        if self.ubicacion == 'CALDAS':
            VentaDiariaReal.objects.create(
                sede=Sede.objects.get(nombre='CALDAS'),
                categoria=CategoriaVenta.objects.get(nombre='CONCESION POLLO'),
                fecha=self.fecha,
                venta_real=self.ValorVenta
            )
        elif self.ubicacion == 'CENTRO':
            VentaDiariaReal.objects.create(
                sede=Sede.objects.get(nombre='CENTRO'),
                categoria=CategoriaVenta.objects.get(nombre='CONCESION POLLO'),
                fecha=self.fecha,
                venta_real=self.ValorVenta
            )
        super().save(*args, **kwargs)

    def __str__(self):
        return f'{self.fecha} - {self.ubicacion} - {self.ValorVenta}'