from django.db.models.signals import post_save
from django.dispatch import receiver
from django.core.mail import EmailMessage, send_mail
from .models import Binnacle
from django.conf import settings
import logging
from django.utils.html import strip_tags
from bs4 import BeautifulSoup
import requests

logger = logging.getLogger(__name__)

#@receiver(post_save, sender=Binnacle)
def notify_employee_on_resolution(sender, instance, created, **kwargs):
    """
    Envía un correo (con imágenes adjuntas) al empleado cuando la bitácora
    pasa a estado 'Resuelto'.
    """
    if instance.status != 'Resuelto':
        logger.debug("Binnacle %s no está en estado 'Resuelto'.", instance.pk)
        return

    employee = getattr(instance, "employee_service", None)
    if not (employee and getattr(employee, "email", None)):
        logger.warning("No hay empleado o email para la bitácora %s.", instance.pk)
        return

    employee_name = (
        f"{getattr(employee, 'first_name', '')} {getattr(employee, 'last_name', '')}"
    ).strip() or "Estimado/a"

    subject = f"✅ Solicitud Resuelta: {instance.title}"
    description_plain = strip_tags(instance.description or "")
    resolved_at = (
        instance.status_changed_at.strftime("%d/%m/%Y %H:%M")
        if instance.status_changed_at
        else "Ahora"
    )
    created_at = (
        instance.created_at.strftime("%d/%m/%Y %H:%M")
        if instance.created_at
        else "Desconocida"
    )


    # Procesar la descripción para eliminar etiquetas <img> del HTML
    soup = BeautifulSoup(instance.description or "", "html.parser")
    for img in soup.find_all("img"):
        img.decompose()  # Eliminar la etiqueta <img> del HTML

    # Convertir la descripción procesada a texto plano
    description_html = str(soup)

    body = f"""<html>
    <head>
        <style>
            body {{
                font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                color: #333;
                line-height: 1.6;
                background-color: #f9f9f9;
                padding: 20px;
            }}
            .container {{
                background-color: #fff;
                border-radius: 8px;
                padding: 20px;
                box-shadow: 0 2px 8px rgba(0,0,0,0.05);
                max-width: 600px;
                margin: auto;
            }}
            h3 {{
                color: #2a8c4a;
            }}
            ul {{
                list-style: none;
                padding-left: 0;
            }}
            li {{
                margin-bottom: 10px;
            }}
            strong {{
                color: #000;
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <p>Hola <strong>{employee_name}</strong>,</p>

            <p>¡Nos alegra informarte que tu solicitud ha sido <strong>resuelta exitosamente</strong>!</p>

            <h3>📋 Detalles de la solicitud:</h3>
            <ul>
                <li><strong>Número de Bitácora:</strong> {instance.pk}</li>
                <li><strong>Título:</strong> {instance.title}</li>
                <li><strong>Categoría:</strong> {instance.Category.name_category if instance.Category else 'No especificada'}</li>
                <li><strong>Tipo de Equipo:</strong> {instance.equipment_service_category.name if instance.equipment_service_category else 'No especificado'}</li>
                <li><strong>Descripción:</strong> {description_html or 'No especificada'}</li>
                <li><strong>Fecha de creación:</strong> {created_at}</li>
                <li><strong>Fecha de resolución:</strong> {resolved_at}</li>
            </ul>

            <p>Si necesitas asistencia adicional Comunicate a nuestros canales de atentción
            celular: <strong>+57 317 5861789</strong> o al correo electrónico: sistemas@mercasur.com.co <strong>  
              </p>

            <p>Saludos cordiales,<br><strong>Equipo de Soporte Técnico</strong></p>

            <p style="font-size: 0.8em; color: #777;">Este es un mensaje automático, por favor no respondas a este correo.</p>
        </div>
    </body>
    </html>
    """

    # Crear email
    email = EmailMessage(
        subject=subject,
        body=body,
        from_email=settings.EMAIL_HOST_USER,
        to=[employee.email],
    )
    email.content_subtype = "html"  # Especificar que el contenido es HTML



    try:
        soup = BeautifulSoup(instance.description or "", "html.parser")
        for img in soup.find_all("img"):
            img_url = img.get("src")
            if not img_url:
                continue

            if not img_url.startswith(("http://", "https://")):
                img_url = f"{settings.SITE_URL}{img_url}"

            try:
                resp = requests.get(img_url, stream=True, timeout=10)
                resp.raise_for_status()
                filename = img_url.split("/")[-1]
                content_type = resp.headers.get("Content-Type", "image/jpeg")
                email.attach(filename, resp.content, content_type)
                logger.info("Imagen adjuntada: %s", filename)
            except Exception as e:
                logger.error("No se pudo adjuntar la imagen %s: %s", img_url, e)
    except Exception as e:
        logger.error("Error al procesar imágenes embebidas: %s", e)

    try:
        email.send(fail_silently=False)
        logger.info("Correo de resolución enviado a %s", employee.email)
    except Exception as e:
        logger.error("Error al enviar el correo: %s", e)