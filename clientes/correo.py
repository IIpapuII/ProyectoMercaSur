from django.core.mail import EmailMessage
from django.template.loader import render_to_string
from django.conf import settings

from django.template import Template, Context, TemplateSyntaxError

def enviar_correo(cliente):
    """
    Envía un correo electrónico basado en un template HTML.

    :param asunto: Asunto del correo.
    :param destinatarios: Lista de correos de destino.
    :param template: Ruta del template HTML para el cuerpo del correo.
    :param contexto: Diccionario de datos para renderizar el template.
    :param remitente: Correo del remitente (opcional). Usa settings.DEFAULT_FROM_EMAIL si no se pasa.
    """

    remitente = settings.EMAIL_HOST_USER
    
    if cliente.Actualizado == False:
        print("Enviado correo Registro")
        asunto = "Bienvenido a mercasur (Registro Exitoso)"
        html_content = render_to_string('clientenuevo.html')
        destinatarios = [cliente.correo]
    else:
        print("Enviado correo Actualización")
        asunto = "Confirmación de Actualización de Información en mercasur"
        html_content = render_to_string('clienteactualizado.html')
        destinatarios = [cliente.correo]
    # Crea el correo
    print(remitente)
    correo = EmailMessage(
        subject=asunto,
        body=html_content,
        from_email=remitente,
        to=destinatarios,
    )

    # Adjunta el contenido HTML
    correo.content_subtype = "html"

    # Envía el correo
    print("Correo Se Envio")
    correo.send()
    print("Correo Se Envio")

def enviar_correo_html(asunto="", destinatarios=None, cuerpo_html="", contexto=None):
    """
    Envía un correo con cuerpo HTML y registra el envío en el modelo CorreoEnviado.

    :param cliente: Instancia del cliente (opcional).
    :param asunto: Asunto del correo.
    :param destinatarios: Lista de correos o string separados por coma.
    :param template_name: Ruta del template HTML.
    :param contexto: Diccionario para renderizar el template.
    :return: Instancia del modelo CorreoEnviado.
    """
    if destinatarios is None:
        destinatarios = []
    if contexto is None:
        contexto = {}

    # Normaliza destinatarios a lista
    if isinstance(destinatarios, str):
        destinatarios = [email.strip() for email in destinatarios.split(",") if email.strip()]
    
    # Renderiza el template
    #cuerpo_html = render_to_string(template_name, contexto)

    # Intenta enviar el correo
    try:
        correo = EmailMessage(
            subject=asunto,
            body=cuerpo_html,
            from_email=settings.EMAIL_HOST_USER,
            to=destinatarios
        )
        correo.content_subtype = "html" 
        correo.send()

    except Exception as e:
        print(e)

def enviar_correo_con_template(asunto,destinatario, template_path, contexto):
    """
    Envía un correo electrónico con cuerpo HTML renderizado desde un template.
    
    :param asunto: Asunto del correo.
    :param destinatario: Lista de destinatarios ['correo@ejemplo.com'] o string único.
    :param template_path: Ruta al template HTML ('emails/codigo_temporal.html').
    :param contexto: Diccionario con los datos para el template.
    :param remitente: Dirección de correo del remitente.
    """
    cuerpo_html = render_to_string(template_name=template_path, context=contexto)
    remitente = settings.EMAIL_HOST_USER
    email = EmailMessage(
        subject=asunto,
        body=cuerpo_html,
        from_email=remitente,
        to= list(destinatario)
    )
    email.content_subtype = "html"  # Para enviar como HTML
    email.send()