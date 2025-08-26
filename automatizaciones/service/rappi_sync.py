# core/services/rappi_sync.py
import os
import time
import math
import logging
from typing import Iterable, List, Dict, Tuple

import requests
from django.db.models import QuerySet
from django.conf import settings

from ..models import Articulos  # ajusta import al path real de tu app

log = logging.getLogger(__name__)

RAPPI_BASE = os.getenv("RAPPI_BASE", "https://services.grability.rappi.com")
RAPPI_CLIENT_ID = os.getenv("RAPPI_CLIENT_ID")
RAPPI_CLIENT_SECRET = os.getenv("RAPPI_CLIENT_SECRET")

# --- utilidades HTTP --- #

def _login() -> str:
    """
    Obtiene Bearer token con client_credentials.
    """
    url = f"{RAPPI_BASE}/api/open-api/login"
    r = requests.post(
        url,
        json={"client_id": RAPPI_CLIENT_ID, "client_secret": RAPPI_CLIENT_SECRET},
        headers={"accept": "application/json", "content-type": "application/json"},
        timeout=60,
    )
    r.raise_for_status()
    token = r.json().get("access_token")
    if not token:
        raise RuntimeError("Login Rappi sin access_token.")
    return token

def _auth_headers(token: str) -> Dict[str, str]:
    return {"Authorization": f"Bearer {token}", "accept": "application/json"}

# --- 1) obtener SKUs de Rappi (catálogo) --- #

def rappi_list_products_skus(token: str, limit: int = 2000, pages: int = 12) -> List[str]:
    """
    Lista SKUs de Rappi desde /catalog/products paginando.
    NOTA: este es catálogo general del aliado; la disponibilidad es por tienda
    y se consulta/activa con los endpoints de availability.
    """
    endpoint = f"{RAPPI_BASE}/api/open-api/v1/catalog/products"
    hdrs = _auth_headers(token)
    skus: List[str] = []

    for i in range(pages):
        offset = i * limit
        params = {"limit": limit, "offset": offset}
        r = requests.get(endpoint, headers=hdrs, params=params, timeout=60)
        if r.status_code >= 500:
            time.sleep(1.5)
            r = requests.get(endpoint, headers=hdrs, params=params, timeout=60)
        r.raise_for_status()

        payload = r.json()
        # Detecta array según contrato (items/data/results/products)
        items = []
        if isinstance(payload, list):
            items = payload
        elif isinstance(payload, dict):
            for key in ("items", "data", "results", "products"):
                if key in payload and isinstance(payload[key], list):
                    items = payload[key]
                    break

        if not items:
            break

        for it in items:
            sku = (it.get("sku") or "").strip()
            if sku:
                skus.append(sku)

        if len(items) < limit:
            break

    # normaliza sin alterar ceros a la izquierda
    return [str(s).strip() for s in skus if s is not None]

# --- 2) cruzar contra ICG por EAN --- #

def _normaliza_ean(ean: str | None) -> str:
    return (ean or "").strip()

def split_icg_vs_rappi(icg_qs: QuerySet, rappi_skus: Iterable[str]) -> Tuple[List[Articulos], List[Articulos]]:
    """
    Separa los artículos ICG en:
      - icg_presentes_en_rappi: EAN aparece como SKU en Rappi.
      - icg_faltantes_en_rappi: EAN NO aparece como SKU en Rappi (candidatos a creación).
    """
    sku_set = {str(s).strip() for s in rappi_skus}
    presentes, faltantes = [], []
    for art in icg_qs.iterator():
        e = _normaliza_ean(art.ean)
        (presentes if e in sku_set else faltantes).append(art)
    return presentes, faltantes

# --- 3) consultar disponibilidad por SKU (store-level) --- #

def rappi_check_availability_by_sku(token: str, store_id: str, sku_list: List[str]) -> Dict[str, dict]:
    """
    Consulta disponibilidad por SKU para una TIENDA específica.
    Doc: POST .../availability/items/status (SKU) / .../availability/items/rappi/status (ID).  # :contentReference[oaicite:3]{index=3}
    Retorna dict mapeado por SKU.
    """
    if not sku_list:
        return {}

    url = f"{RAPPI_BASE}/api/v2/restaurants-integrations-public-api/availability/items/status"
    hdrs = _auth_headers(token)
    # Rappi suele aceptar lotes; segmentamos para no exceder payloads
    chunk = 200
    out: Dict[str, dict] = {}

    for i in range(0, len(sku_list), chunk):
        part = sku_list[i:i+chunk]
        body = {
            "store_id": str(store_id),
            "item_skus": part,   # clave típica para SKU; si tu entorno requiere otro nombre, cámbialo aquí
        }
        r = requests.post(url, headers=hdrs, json=body, timeout=60)
        if r.status_code >= 500:
            time.sleep(1.2)
            r = requests.post(url, headers=hdrs, json=body, timeout=60)
        r.raise_for_status()
        data = r.json()
        # Normaliza respuesta (puede variar por entorno; guarda el objeto tal cual)
        if isinstance(data, list):
            for row in data:
                sku = str(row.get("item_sku") or row.get("sku") or "").strip()
                if sku:
                    out[sku] = row
        elif isinstance(data, dict):
            # a veces la API devuelve un dict con 'items'
            items = data.get("items") or data.get("results") or []
            for row in items:
                sku = str(row.get("item_sku") or row.get("sku") or "").strip()
                if sku:
                    out[sku] = row
    return out

# --- 4) activar/desactivar por SKU (store-level) --- #

def rappi_set_availability_by_sku(token: str, store_integration_id: str, turn_on: List[str], turn_off: List[str]) -> dict:
    """
    Enciende/apaga ítems por SKU para una tienda.
    Doc oficial (payload con store_integration_id, items.turn_on/turn_off).  # :contentReference[oaicite:4]{index=4}
    """
    url = f"{RAPPI_BASE}/api/v2/restaurants-integrations-public-api/availability/stores/items"
    hdrs = _auth_headers(token)
    body = [{
        "store_integration_id": str(store_integration_id),
        "items": {
            "turn_on": turn_on,
            "turn_off": turn_off
        }
    }]
    r = requests.put(url, headers=hdrs, json=body, timeout=60)
    if r.status_code >= 500:
        time.sleep(1.2)
        r = requests.put(url, headers=hdrs, json=body, timeout=60)
    r.raise_for_status()
    return r.json() if r.text else {"status": "ok"}

# --- Orquestador principal --- #

def sincronizar_icg_con_rappi(
    store_id: str,
    store_integration_id: str,
    activar_si_stock_min: int = 1,
    limit_catalogo: int = 2000,
    pages_catalogo: int = 12,
    filtro_icg: Dict | None = None,
) -> dict:
    """
    1) Obtiene token.
    2) Lista SKUs existentes en Rappi (catálogo aliado).
    3) Cruza con Articulos (ICG) por EAN ↔ SKU.
    4) Consulta disponibilidad actual en tienda por SKU.
    5) Decide turn_on / turn_off según stock en ICG y activa en Rappi.

    Retorna resumen con conteos y listas clave.
    """
    token = _login()

    # 1) SKUs en Rappi
    rappi_skus = rappi_list_products_skus(token, limit=limit_catalogo, pages=pages_catalogo)

    # 2) Artículos ICG (puedes filtrar por store_id si tu modelo lo maneja así)
    base_qs = Articulos.objects.all()
    if filtro_icg:
        base_qs = base_qs.filter(**filtro_icg)
    if store_id:
        base_qs = base_qs.filter(store_id=str(store_id))

    presentes, faltantes = split_icg_vs_rappi(base_qs.only("id", "ean", "stock"), rappi_skus)

    # 3) Disponibilidad actual por SKU para los presentes
    sku_presentes = [ _normaliza_ean(a.ean) for a in presentes if a.ean ]
    estado_actual = rappi_check_availability_by_sku(token, store_id, sku_presentes)

    # 4) Decisión de encendido/apagado según stock
    turn_on, turn_off = [], []
    for a in presentes:
        sku = _normaliza_ean(a.ean)
        # Regla simple: stock >= activar_si_stock_min -> encender; si no -> apagar
        if a.stock >= activar_si_stock_min:
            turn_on.append(sku)
        else:
            turn_off.append(sku)

    # 5) Ejecutar activación
    resultado_set = {}
    # Segmenta en lotes por si la lista es grande
    lote = 200
    for i in range(0, len(turn_on), lote):
        resultado_set[f"turn_on_{i//lote}"] = rappi_set_availability_by_sku(
            token, store_integration_id, turn_on[i:i+lote], []
        )
    for i in range(0, len(turn_off), lote):
        resultado_set[f"turn_off_{i//lote}"] = rappi_set_availability_by_sku(
            token, store_integration_id, [], turn_off[i:i+lote]
        )

    resumen = {
        "icg_total": base_qs.count(),
        "rappi_skus": len(rappi_skus),
        "presentes": len(presentes),
        "faltantes": len(faltantes),  # candidatos a creación (no existen en Rappi)
        "turn_on": len(turn_on),
        "turn_off": len(turn_off),
        "resultado_set": resultado_set,
    }
    log.info("Sincronización ICG↔Rappi resumen: %s", resumen)
    return resumen
