# inventarios/services/notifications.py
from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.urls import reverse
from django.utils.html import strip_tags
from django.utils.timezone import localtime

def _from_email():
    return getattr(settings, "DEFAULT_FROM_EMAIL", "notificaciones@mercasur.com.co")

def _safe_get(obj, attr, default=None):
    try:
        return getattr(obj, attr, default)
    except Exception:
        return default

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


def _brand_assets(marca):
    """
    Retorna los activos visuales de la marca con fallback a Mercasur.
    Campos esperados (opcionales) en marca:
      - logo_url / logo / get_logo_url()
      - color_hex
    """
    # Logo
    logo = (
        _safe_get(marca, "logo_url")
        or (_safe_get(marca, "logo") and getattr(marca.logo, "url", None))
        or (_safe_get(marca, "get_logo_url") and marca.get_logo_url())
    )
    logo = logo or "https://notificaciones.mercasur.com.co:9180/logo.png"

    # Color principal
    color = _safe_get(marca, "color_hex", None)
    if not (isinstance(color, str) and color.startswith("#") and len(color) in (4, 7)):
        color = "#2ca646"  # color corporativo fallback

    return {"logo": logo, "color": color}

def _build_admin_url_for_lote(lote, request=None):
    try:
        path = reverse("admin:Compras_sugeridolinea_changelist") + f"?lote__id__exact={lote.id}"
        return request.build_absolute_uri(path) if request else path
    except Exception:
        return "#"

def _html_email_sugerido(proveedor, marca, lote, url_admin):
    assets = _brand_assets(marca)
    marca_nombre = _safe_get(marca, "nombre", "Marca")
    proveedor_nombre = _safe_get(proveedor, "nombre", "Proveedor")
    lote_nombre = _safe_get(lote, "nombre", f"Lote #{lote.id}")
    creado = _safe_get(lote, "creado", None)
    creado_str = localtime(creado).strftime("%Y-%m-%d %H:%M") if creado else ""
    
    # URL de login de la plataforma
    url_login = "https://notificaciones.mercasur.com.co:9180/admin/login/?next=/admin/"

    html = f"""
    <div style="font-family: Arial, sans-serif; color: #333; line-height:1.5;">
      <div style="text-align:center; margin-bottom:20px;">
        <img src="{assets['logo']}" alt="{marca_nombre}" style="max-height:70px;"/>
      </div>

      <h2 style="color:{assets['color']}; margin:0 0 8px 0;">
        Nuevo lote de sugerido #{lote.id}
      </h2>
      <p style="margin:0 0 16px 0; color:#666;">Estructura: <strong>{marca_nombre}</strong> · Proveedor: <strong>{proveedor_nombre}</strong></p>

      <div style="border:1px solid #eee; border-radius:10px; padding:16px; margin:16px 0;">
        <p style="margin:0 0 8px 0;"><strong>Lote:</strong> {lote_nombre}</p>
        <p style="margin:0 0 8px 0;"><strong>ID:</strong> {lote.id}</p>
        {"<p style='margin:0 0 8px 0;'><strong>Creado:</strong> " + creado_str + "</p>" if creado_str else ""}
        <p style="margin:0;">
          Se generó un nuevo lote de sugerido para 
          <strong>{proveedor_nombre}</strong> × <strong>{marca_nombre}</strong>.
        </p>
      </div>

      <div style="text-align:center; margin:24px 0;">
        <a href="{url_login}" 
           style="display:inline-block; background-color:{assets['color']}; color:#fff; 
                  padding:12px 32px; text-decoration:none; border-radius:6px; 
                  font-weight:bold; font-size:16px;">
          Ingresar a la Plataforma
        </a>
      </div>

      <hr style="border:none; border-top:1px solid #eee; margin:24px 0;">
      <p style="font-size:12px; color:#999; text-align:center;">
        mercasur • Cada día mejor
      </p>
    </div>
    """
    return html

def notificar_vendedor_lote_asignado(*, proveedor, marca, lote, request=None):
    """
    Notifica a los vendedores asignados a la combinación (proveedor, marca) del lote,
    enviando un correo con estructura visual de la marca (logo/color) y botón al admin.
    Si no hay emails válidos, omite el envío y finaliza silenciosamente.
    """
    try:
        from Compras.models import AsignacionMarcaVendedor
    except Exception:
        return  # evitar fallos por import

    asignaciones = AsignacionMarcaVendedor.objects.select_related("vendedor__user").filter(
        proveedor=proveedor, marca=marca
    )
    if not asignaciones.exists():
        return

    # Recolectar emails válidos (no vacíos, con '@')
    emails = {
        getattr(a.vendedor.user, "email", "").strip()
        for a in asignaciones
    }
    emails = {e for e in emails if e and "@" in e}

    # Si no hay correos, omitir proceso y finalizar
    if not emails:
        return

    # URL al admin filtrado por el lote
    url = _build_admin_url_for_lote(lote, request=request)

    marca_nombre = _safe_get(marca, "nombre", "Marca")
    proveedor_nombre = _safe_get(proveedor, "nombre", "Proveedor")
    asunto = f"[Sugerido] Nuevo lote #{lote.id} · {marca_nombre} · {proveedor_nombre}"

    # HTML + Texto plano
    html_body = _html_email_sugerido(proveedor, marca, lote, url)
    text_body = (
        f"Nuevo lote de sugerido #{lote.id}\n"
        f"Estructura: {marca_nombre} · Proveedor: {proveedor_nombre}\n\n"
        f"Lote: {_safe_get(lote, 'nombre', f'Lote #{lote.id}')}\n"
        f"ID: {lote.id}\n\n"
        f"Revisar en el panel: {url}\n\n"
        "Mercasur • Cada día mejor"
    )

    # Envío
    msg = EmailMultiAlternatives(
        subject=asunto,
        body=text_body,
        from_email=_from_email(),
        to=list(emails),
        reply_to=[_from_email()],
    )
    msg.attach_alternative(html_body, "text/html")
    try:
        msg.send(fail_silently=True)
    except Exception:
        # Fallback ultra simple si algo sale mal con HTML
        from django.core.mail import send_mail
        send_mail(asunto, text_body, _from_email(), list(emails), fail_silently=True)