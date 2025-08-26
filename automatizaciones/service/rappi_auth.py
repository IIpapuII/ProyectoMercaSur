# utils/rappi_auth.py
import os
import time
import requests
from typing import Optional
from django.conf import settings

try:
    # si estás en Django, toma valores desde settings si existen
    from django.conf import settings
except Exception:
    settings = None


class RappiAuthError(RuntimeError):
    pass


# cache simple en memoria de proceso
_TOKEN_CACHE = {"value": None, "exp": 0.0}


def _get_setting(name: str, default: Optional[str] = None) -> Optional[str]:
    """Lee primero de Django settings y luego de variables de entorno."""
    if settings and hasattr(settings, name):
        return getattr(settings, name)
    return os.getenv(name, default)


def get_rappi_token(force_refresh: bool = False, timeout: int = 60) -> str:
    """
    Devuelve un Bearer token válido para la API de Rappi.
    - Cachea el token hasta su expiración (usa 'expires_in' si viene en la respuesta).
    - Si `force_refresh=True`, ignora el cache y vuelve a loguear.
    Lanza RappiAuthError si falta configuración o la petición falla.
    """
    
    base = _get_setting("RAPPI_BASE", "https://services.grability.rappi.com").rstrip("/")
    client_id = settings.RAPPI_CLIENT_ID
    client_secret = settings.RAPPI_CLIENT_SECRET

    if not client_id or not client_secret:
        raise RappiAuthError("Faltan credenciales: define RAPPI_CLIENT_ID y RAPPI_CLIENT_SECRET.")

    now = time.time()
    if not force_refresh and _TOKEN_CACHE["value"] and now < _TOKEN_CACHE["exp"]:
        return _TOKEN_CACHE["value"]

    url = f"{base}/api/open-api/login"
    resp = requests.post(
        url,
        json={"client_id": client_id, "client_secret": client_secret},
        headers={"accept": "application/json", "content-type": "application/json"},
        timeout=timeout,
    )
    try:
        resp.raise_for_status()
    except requests.HTTPError as e:
        raise RappiAuthError(f"Error autenticando en Rappi: {resp.status_code} {resp.text}") from e

    data = resp.json() or {}
    token = data.get("access_token")
    if not token:
        raise RappiAuthError("Respuesta de login sin 'access_token'.")

    # calcula expiración (fallback seguro ~50 min si no viene)
    expires_in = int(data.get("expires_in", 3000))
    _TOKEN_CACHE["value"] = token
    _TOKEN_CACHE["exp"] = now + max(expires_in - 30, 60)  # margen de 30s

    return token


def rappi_auth_headers(force_refresh: bool = False) -> dict:
    """Headers listos para llamadas autenticadas."""
    return {
        "Authorization": f"Bearer {get_rappi_token(force_refresh=force_refresh)}",
        "accept": "application/json",
    }
