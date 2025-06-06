# Puedes poner esto en un archivo utils.py o al inicio de tasks.py
from django.template import Template, Context, TemplateSyntaxError
from django.core.mail import EmailMessage
from django.conf import settings

def enviar_correo_renderizado(asunto="", destinatarios=None, template_html_string="", contexto=None):
    """
    Renderiza una plantilla HTML string con un contexto y envía el correo.

    :param asunto: Asunto del correo.
    :param destinatarios: Lista de correos o string separados por coma.
    :param template_html_string: String que contiene la plantilla HTML.
    :param contexto: Diccionario para renderizar el template.
    :return: True si el envío fue exitoso, False en caso contrario.
    :raises: TemplateSyntaxError si la plantilla es inválida, Exception para errores de envío.
    """
    if destinatarios is None:
        destinatarios = []
    if contexto is None:
        contexto = {}

    # Normaliza destinatarios a lista
    if isinstance(destinatarios, str):
        destinatarios = [email.strip() for email in destinatarios.split(",") if email.strip() and '@' in email.strip()]

    if not destinatarios:
        print("Advertencia: No hay destinatarios válidos para enviar.")
        return False # O lanzar un error específico

    # Renderiza la plantilla HTML
    try:
        if not template_html_string:
             raise ValueError("La plantilla HTML (cuerpo_html) no puede estar vacía.")
        template = Template(template_html_string)
        context_obj = Context(contexto)
        cuerpo_renderizado = template.render(context_obj)
    except TemplateSyntaxError as e_template:
        print(f"Error de sintaxis en la plantilla: {e_template}")
        raise # Re-lanza la excepción para que la tarea Celery la capture
    except ValueError as e_value:
        print(f"Error en plantilla: {e_value}")
        raise
    except Exception as e_render:
        print(f"Error inesperado al renderizar plantilla: {e_render}")
        raise # Re-lanza para captura genérica

    # Intenta enviar el correo
    try:
        correo = EmailMessage(
            subject=asunto,
            body=cuerpo_renderizado, # Usa el cuerpo renderizado
            from_email=settings.DEFAULT_FROM_EMAIL, # Usa la configuración de Django
            to=destinatarios
        )
        correo.content_subtype = "html"
        sent_count = correo.send(fail_silently=False) # Lanza excepción si falla
        print(f"Correo enviado a {sent_count} destinatarios.")
        return sent_count > 0
    except Exception as e_send:
        print(f"Error al enviar correo: {e_send}")
        raise # Re-lanza la excepción para que Celery la maneje