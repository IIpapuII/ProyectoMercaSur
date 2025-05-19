from celery import shared_task
from django.conf import settings
from .models import CodigoTemporal
from .correo import enviar_correo_con_template
import ast

@shared_task
def generar_enviar_codigo_temporal():
    """
    Genera un código temporal y lo envía al area correspondiente.
    """
    # Generar el código temporal
    try:
        codigo_temporal = CodigoTemporal.objects.create()
        destinatorio = [email.strip() for email in settings.EMAIL_CODIGO_COLABORADOR.split(',') if email.strip()]
        print(f"Destinatarios: {destinatorio}")
        enviar_correo_con_template(
            asunto="Código Temporal Generado",
            destinatario= destinatorio,
            template_path='codigo_temporal.html',
            contexto={
                'codigo': codigo_temporal.codigo,
                'fecha_expiracion':codigo_temporal.fecha_vencimiento,
            }
        )
        # Aquí puedes agregar la lógica para enviar el código al área correspondiente
        # Por ejemplo, enviar un correo electrónico o una notificación
        print(f"Código temporal generado: {codigo_temporal.codigo}")
    except Exception as e:
        print(f"Error al generar o enviar el código temporal: {e}")
    