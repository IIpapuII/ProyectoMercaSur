# services/rappi.py
from decimal import Decimal
import requests

RAPPI_BASE_URL = "https://services.{server}/api/open-api/v1"
RAPPI_TIMEOUT = 25


class RappiError(Exception):
    pass


def _auth_headers(bearer_token: str) -> dict:
    return {
        "Authorization": f"Bearer {bearer_token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


def _resolve_rappi_store_id(
    *,
    local_store_id: str | int,
    local_to_name: dict[str, str],
    name_to_rappi: dict[str, int],
) -> int:
    """
    1) Convierte el store_id local (90017xxxx) a nombre (p.ej. 'Mercasur, Centro')
    2) Convierte nombre a ID interno Rappi (21xxx)
    """
    if local_store_id is None:
        raise RappiError("El Articulo no tiene store_id local.")

    key = str(local_store_id).strip()

    if key not in local_to_name:
        raise RappiError(
            f"No encontré el nombre de tienda para store_id local='{key}'. "
            "Agrega este ID al diccionario local_to_name."
        )

    store_name = local_to_name[key]

    if store_name not in name_to_rappi:
        raise RappiError(
            f"No encontré el ID de Rappi para la tienda '{store_name}'. "
            "Agrega este nombre al diccionario name_to_rappi."
        )

    return int(name_to_rappi[store_name])


def _get_ids_from_sku(server: str, token: str, sku: str | None) -> dict | None:
    """
    Busca en GET /catalog/products/sku?skus=<sku>
    Devuelve: {"productId": int|None, "listingId": int|None}
      - productId: ID global de producto (si lo trae)
      - listingId: ID del ítem/listado (campo 'id' en la respuesta)
    """
    if not sku:
        return None

    url = f"https://services.{server}/api/open-api/v1/catalog/products/sku"
    r = requests.get(
        url,
        headers=_auth_headers(token),
        params={"skus": str(sku).strip()},
        timeout=RAPPI_TIMEOUT,
    )
    if r.status_code != 200:
        return None

    data = r.json() or []

    def pick(item):
        pid = item.get("productId")
        lid = item.get("id")
        return {
            "productId": int(pid) if pid else None,
            "listingId": int(lid) if lid else None,
        }

    # Respuesta como lista
    if isinstance(data, list):
        for item in data:
            if str(item.get("sku", "")).strip() == str(sku).strip():
                return pick(item)

    # Respuesta envuelta en {"data":[...]} o {"items":[...]}
    if isinstance(data, dict):
        items = data.get("data") or data.get("items") or []
        for item in items:
            if str(item.get("sku", "")).strip() == str(sku).strip():
                return pick(item)

    return None


def _to_int_money(value) -> int:
    """
    Convierte Decimal/float/int a entero (p. ej. 21650).
    Ajusta si tu backend requiere centavos.
    """
    if value is None:
        return 0
    try:
        return int(round(float(value)))
    except Exception:
        return 0


def _put_inventory(server: str, token: str, store_id: int, product_or_listing_id: int, payload: dict) -> requests.Response:
    url = (
        f"https://services.{server}/api/open-api/v1/catalog/stores/"
        f"{store_id}/inventory/{product_or_listing_id}"
    )
    return requests.put(url, headers=_auth_headers(token), json=payload, timeout=RAPPI_TIMEOUT)


def update_inventory_one_by_one(
    *,
    server: str,
    token: str,
    articulo,                       # instancia de Articulos
    local_to_name: dict[str, str],  # 90017xxxx -> "Mercasur, Centro"
    name_to_rappi: dict[str, int],  # "Mercasur, Centro" -> 21128
) -> dict:
    """
    Actualiza UN producto en Rappi:
      - Si stock <= 0: NO actualiza en Rappi; marca disponible=False y modificado=False localmente.
      - Resuelve store_id de Rappi a partir del store_id local.
      - Obtiene IDs usando /catalog/products/sku?skus= (con EAN y fallback a code):
          * productId (global) y listingId (id)
      - Intenta PUT con productId; si 404, reintenta con listingId.
    """
    # 0) Si stock <= 0, NO enviar a Rappi
    stock = int(getattr(articulo, "stock", 0))
    if stock <= 0:
        # marcar flags locales si existen
        try:
            if hasattr(articulo, "is_available"):
                articulo.is_available = False
            if hasattr(articulo, "modificado"):
                articulo.modificado = False
            articulo.save(update_fields=["is_available", "modificado"])
        except Exception:
            pass

        return {
            "ok": True,
            "skipped": True,
            "reason": "stock <= 0 (no se envía actualización a Rappi)",
            "store_local": str(getattr(articulo, "store_id", "")),
            "ean": getattr(articulo, "ean", None),
        }

    # 1) store_id de Rappi a partir del store_id local
    rappi_store_id = _resolve_rappi_store_id(
        local_store_id=getattr(articulo, "store_id", None),
        local_to_name=local_to_name,
        name_to_rappi=name_to_rappi,
    )

    # 2) IDs desde endpoint de SKU (usando EAN como sku; fallback a code)
    ean = getattr(articulo, "ean", None)
    code = getattr(articulo, "code", None)

    ids = _get_ids_from_sku(server, token, ean) or _get_ids_from_sku(server, token, code)
    if not ids:
        raise RappiError(
            f"No encontré IDs en Rappi usando el endpoint de SKU con EAN='{ean}' ni con Code='{code}'."
        )

    product_id = ids.get("productId")
    listing_id = ids.get("listingId")

    if not product_id and not listing_id:
        raise RappiError(
            f"El endpoint de SKU no devolvió ni productId ni listingId para EAN='{ean}' / Code='{code}'."
        )

    # 3) payload de inventario
    price = _to_int_money(getattr(articulo, "price", 0))
    discount = _to_int_money(getattr(articulo, "discount_price", 0))
    sale_price = discount if discount > 0 else price

    payload = {"stock": stock, "price": price, "sale_price": sale_price}

    # 4) PUT inventario: probar productId y si 404, probar listingId
    tried = []
    resp = None

    if product_id:
        resp = _put_inventory(server, token, rappi_store_id, product_id, payload)
        tried.append({"type": "productId", "value": product_id, "status": resp.status_code})
        if resp.status_code == 404 and listing_id:
            # reintento con listingId
            resp = _put_inventory(server, token, rappi_store_id, listing_id, payload)
            tried.append({"type": "listingId", "value": listing_id, "status": resp.status_code})

    elif listing_id:
        resp = _put_inventory(server, token, rappi_store_id, listing_id, payload)
        tried.append({"type": "listingId", "value": listing_id, "status": resp.status_code})

    if resp is None or resp.status_code not in (200, 201, 202):
        body = resp.text if resp is not None else "no response"
        raise RappiError(f"PUT inventario falló. Intentos={tried}. Respuesta={body}")

    data = (
        resp.json()
        if resp.headers.get("content-type", "").lower().startswith("application/json")
        else {"raw": resp.text}
    )

    # 5) marcar disponible localmente (opcional)
    try:
        if hasattr(articulo, "is_available"):
            articulo.is_available = stock > 0
        if hasattr(articulo, "modificado"):
            articulo.modificado = False
        articulo.save(update_fields=["is_available", "modificado"])
    except Exception:
        pass

    return {
        "ok": True,
        "skipped": False,
        "store_local": str(getattr(articulo, "store_id", "")),
        "store_rappi": rappi_store_id,
        "used": tried[-1] if tried else None,   # cuál ID terminó usando
        "ids_found": {"productId": product_id, "listingId": listing_id},
        "sent": payload,
        "response": data,
        "attempts": tried,
    }
