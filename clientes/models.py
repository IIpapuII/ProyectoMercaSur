from django.db import models

class RegistroCliente(models.Model):
    primer_apellido = models.CharField(max_length=100)
    segundo_apellido = models.CharField(max_length=100, blank=True)
    primer_nombre = models.CharField(max_length=100)
    segundo_nombre = models.CharField(max_length=100, blank=True)
    numero_documento = models.CharField(max_length=50)
    fecha_nacimiento = models.DateField()
    correo = models.EmailField()
    telefono = models.CharField(max_length=20, blank=True, null=True)
    celular = models.CharField(max_length=20)
    tipo_via = models.CharField(max_length=50)
    direccion = models.CharField(max_length=255)
    barrio = models.CharField(max_length=100)
    ciudad = models.CharField(max_length=100)

    mascota = models.CharField(max_length=50, choices=[
        ('perro', 'Perro'),
        ('gato', 'Gato'),
        ('otro', 'Otro'),
        ('ninguna', 'Ninguna')
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
    longitud = models.FloatField(null=True, blank=True)
    latitud = models.FloatField(null=True, blank=True)
    firma_base64 = models.TextField(blank=True)  # Aquí se guarda la imagen como base64

    fecha_registro = models.DateTimeField(auto_now_add=True)
    fidelizacion = models.BooleanField(default=False)
    tipocliente = models.CharField(max_length=50, null=True, blank=True)
    fecha_modificacion = models.DateTimeField(auto_now=True)
    Actualizado = models.BooleanField(default=False)
    creadoICG = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.primer_nombre} {self.primer_apellido}"
    class Meta:
        verbose_name = "Registro de cliente"
        verbose_name_plural = "Registros de Clientes"
        db_table = 'RegistroCliente'
        unique_together = ('numero_documento',)
        ordering = ['-fecha_registro']

class ZonaPermitida(models.Model):
    """
    Representa una zona geográfica permitida definida por un punto central
    (latitud/longitud) y un radio máximo.
    """
    nombre = models.CharField(
        max_length=100,
        verbose_name="Nombre Descriptivo",
        help_text="Un nombre para identificar fácilmente la zona (ej: 'Oficina Principal', 'Almacén Norte')"
    )
    latitude = models.FloatField(
        verbose_name="Latitud",
        help_text="Coordenada de latitud del centro de la zona (grados decimales)."
    )
    longitude = models.FloatField(
        verbose_name="Longitud",
        help_text="Coordenada de longitud del centro de la zona (grados decimales)."
    )
    max_distance = models.PositiveIntegerField(
        verbose_name="Distancia Máxima (Metros)",
        help_text="Radio máximo permitido en metros desde el punto central."
    )
    activa = models.BooleanField(
        default=True,
        verbose_name="Zona Activa",
        help_text="Desmarca para desactivar esta zona sin borrarla."
    )
    creado = models.DateTimeField(auto_now_add=True)
    actualizado = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Zona Permitida"
        verbose_name_plural = "Zonas Permitidas"
        ordering = ['nombre'] 

    def __str__(self):
        return f"{self.nombre} ({self.latitude}, {self.longitude}) - {self.max_distance}m"

class barrio(models.Model):
    """
    Representa un barrio o localidad en una ciudad.
    """
    nombre = models.CharField(max_length=100, unique=True)
    ciudad = models.CharField(max_length=100)

    def __str__(self):
        return f"{self.nombre}, {self.ciudad}"