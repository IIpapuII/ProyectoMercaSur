import time
import requests
import pandas as pd

def exportar_productos_basicos_excel(
    output_path: str = "productos_basicos_12_offsets.xlsx",
    limit: int = 2000,
    offsets: int = 12,
    base_url: str = "https://services.grability.rappi.com",
    token: str | None = None,
    client_id: str | None = None,
    client_secret: str | None = None,
    pause_seconds: float = 0.4,
    timeout: int = 60
) -> str:
    """
    Descarga productos desde /api/open-api/v1/catalog/products paginando por offset
    y exporta a Excel SOLO con las columnas: id, ean, sku, name.

    - Si 'token' no se provee, intentará autenticarse con 'client_id' y 'client_secret'.
    - Paginación: 'offsets' páginas, cada una de tamaño 'limit' (offset = i * limit).
    - Se detiene antes si una página trae menos registros que 'limit'.

    Retorna: ruta del archivo Excel generado (output_path).
    """

    def login() -> str:
        """Obtiene Bearer token con client_credentials."""
        if not client_id or not client_secret:
            raise RuntimeError("Falta 'token' o credenciales 'client_id'/'client_secret' para login.")
        url = f"{base_url}/api/open-api/login"
        r = requests.post(url, json={"client_id": client_id, "client_secret": client_secret},
                          headers={"accept": "application/json", "content-type": "application/json"},
                          timeout=timeout)
        r.raise_for_status()
        return r.json().get("access_token")

    def extract_items(payload):
        """Ubica el array de productos sin asumir una clave fija."""
        if isinstance(payload, list):
            return payload
        if isinstance(payload, dict):
            for k in ("items", "data", "results", "products"):
                if k in payload and isinstance(payload[k], list):
                    return payload[k]
        return []

    def pick_basic_fields(item: dict) -> dict:
        """Solo los campos solicitados, ajusta aquí si vienen anidados."""
        return {
            "id": item.get("id"),
            "ean": item.get("ean"),
            "sku": item.get("sku"),
            "name": item.get("name"),
        }

    # 1) Token
    bearer = token or login()
    headers = {"Authorization": f"Bearer {bearer}", "accept": "application/json"}

    # 2) Bucle de paginación
    rows = []
    endpoint = f"{base_url}/api/open-api/v1/catalog/products"

    for i in range(offsets):
        offset_val = i * limit
        params = {"limit": limit, "offset": offset_val}

        resp = requests.get(endpoint, headers=headers, params=params, timeout=timeout)
        # Reintento simple si hay 5xx
        if resp.status_code >= 500:
            time.sleep(1.5)
            resp = requests.get(endpoint, headers=headers, params=params, timeout=timeout)

        resp.raise_for_status()
        items = extract_items(resp.json())

        for it in items:
            rows.append(pick_basic_fields(it))

        # Si vino incompleta, no hay más páginas
        if len(items) < limit:
            break

        if pause_seconds:
            time.sleep(pause_seconds)

    # 3) DataFrame: forzar ean/sku/name a string para no perder ceros
    df = pd.DataFrame(rows, columns=["id", "ean", "sku", "name"])
    if not df.empty:
        for col in ("ean", "sku", "name"):
            if col in df.columns:
                df[col] = df[col].astype("string")

    # 4) Exportar a Excel
    with pd.ExcelWriter(output_path, engine="xlsxwriter") as writer:
        df.to_excel(writer, sheet_name="productos", index=False)

    return output_path