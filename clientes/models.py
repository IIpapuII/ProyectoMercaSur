from django.db import models

class RegistroCliente(models.Model):
    primer_apellido = models.CharField(max_length=100)
    segundo_apellido = models.CharField(max_length=100, blank=True)
    primer_nombre = models.CharField(max_length=100)
    segundo_nombre = models.CharField(max_length=100, blank=True)
    numero_documento = models.CharField(max_length=50)
    fecha_nacimiento = models.DateField()
    correo = models.EmailField()
    telefono = models.CharField(max_length=20, blank=True)
    celular = models.CharField(max_length=20)
    tipo_via = models.CharField(max_length=50)
    direccion = models.CharField(max_length=255)
    barrio = models.CharField(max_length=100)
    ciudad = models.CharField(max_length=100)

    mascota = models.CharField(max_length=50, choices=[
        ('perro', 'Perro'),
        ('gato', 'Gato'),
        ('otro', 'Otro')
    ])
    otra_mascota = models.CharField(max_length=100, blank=True)

    preferencias_email = models.BooleanField(default=False)
    preferencias_whatsapp = models.BooleanField(default=False)
    preferencias_sms = models.BooleanField(default=False)
    preferencias_redes_sociales = models.BooleanField(default=False)
    preferencias_llamada = models.BooleanField(default=False)
    preferencias_ninguna = models.BooleanField(default=False)

    acepto_politica = models.BooleanField(default=False)

    ip_usuario = models.GenericIPAddressField(null=True, blank=True)
    logitud = models.FloatField(null=True, blank=True)
    latitud = models.FloatField(null=True, blank=True)
    firma_base64 = models.TextField(blank=True)  # Aquí se guarda la imagen como base64

    fecha_registro = models.DateTimeField(auto_now_add=True)
    fidelizacion = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.primer_nombre} {self.primer_apellido}"
    class Meta:
        verbose_name = "Registro de cliente"
        verbose_name_plural = "Registros de Clientes"
        db_table = 'RegistroCliente'
        unique_together = ('numero_documento',)
        ordering = ['-fecha_registro']