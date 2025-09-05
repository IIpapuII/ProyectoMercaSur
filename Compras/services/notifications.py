# inventarios/services/notifications.py
from django.core.mail import send_mail
from django.urls import reverse
from django.conf import settings

def _from_email():
    return getattr(settings, "DEFAULT_FROM_EMAIL", "no-reply@mercasur.com.co")


def notificar_proveedor_lote_enviado(*, proveedor_nombre: str, lote, request=None):
    """
    Envía correo al proveedor cuando un lote pasa a ENVIADO.
    Aquí usamos proveedor por nombre; si tienes emails por proveedor, resuélvelos.
    """
    asunto = f"[Sugerido] Nuevo lote #{lote.id} disponible"
    # Enlace al admin filtrado por proveedor (si el proveedor entra por admin)
    url = ""
    try:
        url = request.build_absolute_uri(
            reverse("admin:inventarios_sugeridolinea_changelist") + f"?proveedor={proveedor_nombre}"
        )
    except Exception:
        pass
    cuerpo = (
        f"Estimado proveedor {proveedor_nombre},\n\n"
        f"Se ha generado el lote #{lote.id} ({lote.nombre}). "
        f"Puede revisar y proponer ajustes en el enlace:\n{url}\n\n"
        f"Saludos,\nMercasur"
    )
    # TODO: resolver email real del proveedor
    destinatarios = [getattr(settings, "COMPRAS_TEST_EMAIL", "compras@mercasur.com.co")]
    send_mail(asunto, cuerpo, _from_email(), destinatarios, fail_silently=True)


def notificar_compras_respuesta_proveedor(*, proveedor_nombre: str, lineas, request=None):
    asunto = f"[Sugerido] {proveedor_nombre} envió respuesta"
    cuerpo = (
        f"El proveedor {proveedor_nombre} envió cambios sobre {lineas.count()} línea(s). "
        f"Revise el Admin para aprobar o rechazar."
    )
    destinatarios = [getattr(settings, "COMPRAS_TEST_EMAIL", "compras@mercasur.com.co")]
    send_mail(asunto, cuerpo, _from_email(), destinatarios, fail_silently=True)
