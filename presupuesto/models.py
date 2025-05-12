from django.db import models

# Create your models here.

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

    def __str__(self):
        return f'{self.fecha} - {self.ubicacion} - {self.ValorVenta}'