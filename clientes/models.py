from datetime import timedelta
from django.utils import timezone
import random
import string
from django.db import models
from django.forms import ValidationError
import uuid

class SecuenciaCodCliente(models.Model):
    ultimo_codigo = models.IntegerField(default=51500001)  # El anterior al inicial
    rango_maximo = models.IntegerField(default=545000000)  # Puedes cambiar este valor

    class Meta:
        verbose_name = "Secuencia de Código de Cliente"
        verbose_name_plural = "Secuencias de Códigos de Clientes"
        db_table = 'secuencia_cod_cliente'
        ordering = ['-ultimo_codigo']
    def __str__(self):
        return f"Último código: {self.ultimo_codigo}, Rango máximo: {self.rango_maximo}"

class RegistroCliente(models.Model):
    codcliente = models.IntegerField(blank=True, null=True, unique=True)
    primer_apellido = models.CharField(max_length=100)
    segundo_apellido = models.CharField(max_length=100, blank=True, null=True)
    primer_nombre = models.CharField(max_length=100)
    segundo_nombre = models.CharField(max_length=100, blank=True, null=True)
    numero_documento = models.CharField(max_length=50)
    fecha_nacimiento = models.DateField()
    correo = models.EmailField(blank=True, null=True)
    telefono = models.CharField(max_length=20, blank=True, null=True)
    celular = models.CharField(max_length=20,blank=True, null=True)
    tipo_via = models.CharField(max_length=50,blank=True, null=True)
    direccion = models.CharField(max_length=255,blank=True, null=True)
    barrio = models.CharField(max_length=100,blank=True, null=True)
    ciudad = models.CharField(max_length=100,blank=True, null=True)
    genero = models.CharField(max_length=50, choices=[
        ('MUJER', 'Mujer'),
        ('HOMBRE', 'Hombre'),
        ('NO APLICA', 'No Aplica')
    ], blank=True, null=True)
    mascota = models.CharField(max_length=50, choices=[
        ('PERRO', 'Perro'),
        ('GATO', 'Gato'),
        ('OTROS', 'Otro'),
        ('NO TIENE', 'Ninguna')
    ], blank=True)
    otra_mascota = models.CharField(max_length=100, blank=True,null=True)

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
    correo_notificacion = models.BooleanField(default=False)
    punto_compra = models.CharField(max_length=100, null=True, blank=True)

    def __str__(self):
        return f"{self.primer_nombre} {self.primer_apellido}"
    class Meta:
        verbose_name = "Registro de cliente"
        verbose_name_plural = "Registros de Clientes"
        db_table = 'RegistroCliente'
        unique_together = ('numero_documento','codcliente')
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
    ciudad = models.CharField(max_length=100, null=True, blank=True)

    def __str__(self):
        return f"{self.nombre}, {self.ciudad}"
    

class CodigoTemporal(models.Model):
    @staticmethod
    def generar_codigo_alfanumerico():
        numeros = ''.join(random.choice(string.digits) for _ in range(4))
        letras = ''.join(random.choice(string.ascii_uppercase) for _ in range(3))
        return f'{numeros}{letras}'

    codigo = models.CharField(max_length=7, unique=True, editable=False,  blank=True, null=True)
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    fecha_vencimiento = models.DateTimeField(null=True, blank=True)

    def clean(self):
        # Verificar si ya existe un código creado hoy
        hoy_inicio = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
        hoy_fin = hoy_inicio + timedelta(days=1)
        if CodigoTemporal.objects.filter(fecha_creacion__gte=hoy_inicio, fecha_creacion__lt=hoy_fin).exists():
            raise ValidationError("Solo se puede crear un código por día.")

    def save(self, *args, **kwargs):
        # Llamar a clean() antes de guardar para realizar la validación
        self.clean()

        # Eliminar códigos vencidos globalmente
        if not self.pk:
            CodigoTemporal.objects.filter(fecha_vencimiento__lte=timezone.now()).delete()
            # Invalidar cualquier código activo existente
            CodigoTemporal.objects.filter(fecha_vencimiento__gt=timezone.now()).update(fecha_vencimiento=timezone.now())

        if not self.codigo:  # Asegurarse de que el código se genere si es una nueva instancia
            self.codigo = self.generar_codigo_alfanumerico()
            self.fecha_creacion = timezone.now()
            self.fecha_vencimiento = self.fecha_creacion + timedelta(hours=10)
        super().save(*args, **kwargs)

    def es_valido(self):
        return self.fecha_vencimiento is not None and timezone.now() < self.fecha_vencimiento

    def __str__(self):
        return self.codigo
    
    class Meta:
        verbose_name = 'Código Temporal'
        verbose_name_plural = "Códigos Temporales"
        
class LogComportamientoCliente(models.Model): # Renombrado a español
    class TipoEvento(models.TextChoices): # Renombrado y opciones en español
        # Ciclo de vida de la Página/Formulario
        CARGA_PAGINA = 'PAGE_LOAD', 'Página Cargada'
        FORMULARIO_DESMONTADO = 'FORM_UNMOUNTED', 'Formulario Desmontado/Componente Destruido'
        FORMULARIO_ABANDONADO = 'FORM_ABANDONED', 'Formulario Abandonado (Antes de Descargar)'
        ACCION_REINICIO_FORMULARIO = 'FORM_RESET_ACTION', 'Formulario Reiniciado por Usuario'

        # Verificación de Documento
        DOCUMENTO_INPUT_BLUR = 'DOCUMENT_INPUT_BLUR', 'Input de Documento Perdió Foco'
        VALIDACION_DOCUMENTO_FALLIDA_CLIENTE = 'DOCUMENT_VALIDATION_FAILED_CLIENT_SIDE', 'Validación de Documento Fallida (Cliente)'
        INTENTO_VERIFICACION_DOCUMENTO = 'DOCUMENT_VERIFICATION_ATTEMPT', 'Intento de Verificación de Documento (API)'
        RESULTADO_VERIFICACION_DOCUMENTO = 'DOCUMENT_VERIFICATION_RESULT', 'Resultado Verificación de Documento (API)' # data: {existe: bool, exito: bool, error?: str}

        # Activación de Formulario e Interacción de Campos
        FORMULARIO_ACTIVADO = 'FORM_ACTIVATED', 'Formulario Principal Activado' # Después de verificar doc
        CAMPO_ENFOCADO = 'FIELD_FOCUS', 'Campo Enfocado' # data: {nombre_campo: str}
        CAMPO_DESENFOCADO = 'FIELD_BLUR', 'Campo Perdió Foco (Valor Cambiado/Significativo)' # data: {nombre_campo: str, longitud_valor?: int, fragmento_valor?: str}
        FALLA_CARGA_BARRIOS = 'BARRIOS_LOAD_FAILURE', 'Falla al Cargar Lista de Barrios'
        RESULTADO_VALIDACION_EDAD = 'AGE_VALIDATION_RESULT', 'Resultado Validación de Edad' # data: {valido: bool, edad_calculada?: int}

        # Interacciones con Modales
        MODAL_POLITICA_ABIERTO = 'POLICY_MODAL_OPENED', 'Modal de Política Abierto'
        POLITICA_CONFIRMADA = 'POLICY_CONFIRMED', 'Política Confirmada por Usuario'
        MODAL_FIDELIZACION_ABIERTO = 'FIDELIZATION_MODAL_OPENED', 'Modal de Fidelización Abierto'
        FIDELIZACION_CONFIRMADA = 'FIDELIZATION_CONFIRMED', 'Fidelización Confirmada'
        FIDELIZACION_RECHAZADA = 'FIDELIZATION_DECLINED', 'Fidelización Rechazada'

        # Firma
        FIRMA_SOLICITADA = 'SIGNATURE_REQUESTED', 'Panel de Firma Mostrado'

        # Envío de Formulario
        INTENTO_ENVIO_FORMULARIO = 'FORM_SUBMIT_ATTEMPT', 'Intento de Envío de Formulario'
        ERROR_VALIDACION_ENVIO_FORMULARIO = 'FORM_SUBMIT_VALIDATION_ERROR', 'Error de Validación al Enviar Formulario (Cliente)' # data: {mensaje_error: str, campo?: str}
        ENVIO_FORMULARIO_EXITOSO = 'FORM_SUBMIT_SUCCESS', 'Envío de Formulario Exitoso (API)' # data: {accion: 'crear'/'actualizar'}
        FALLA_ENVIO_FORMULARIO = 'FORM_SUBMIT_FAILURE', 'Falla en Envío de Formulario (API)' # data: {accion: 'crear'/'actualizar', mensaje_error?: str, codigo_estado?: int}

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    id_sesion = models.CharField(max_length=100, db_index=True, help_text="ID de sesión generado en el frontend")
    # usuario = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, help_text="Usuario autenticado, si está disponible")
    numero_documento_cliente = models.CharField(max_length=20, null=True, blank=True, db_index=True, help_text="Número de documento ingresado por el usuario")
    tipo_evento = models.CharField(max_length=50, choices=TipoEvento.choices)
    timestamp_evento = models.DateTimeField(auto_now_add=True, verbose_name="Fecha y Hora del Evento")
    datos_evento = models.JSONField(null=True, blank=True, help_text="Datos específicos del contexto para el evento")
    direccion_ip = models.GenericIPAddressField(null=True, blank=True, verbose_name="Dirección IP")
    user_agent = models.TextField(null=True, blank=True, verbose_name="Agente de Usuario") # User Agent
    url_actual = models.URLField(max_length=1024, null=True, blank=True, help_text="URL en el momento del evento")

    def __str__(self):
        return f"{self.id_sesion} - {self.get_tipo_evento_display()} en {self.timestamp_evento.strftime('%Y-%m-%d %H:%M:%S')}"

    class Meta:
        ordering = ['-timestamp_evento']
        verbose_name = 'Registro de Comportamiento del Cliente'
        verbose_name_plural = 'Registros de Comportamiento del Cliente'

