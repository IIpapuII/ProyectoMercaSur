from django.db import transaction
import pandas as pd
from ..models import Articulos, DescuentoDiario, APILogRappi
import http.client
import json
from datetime import datetime
from django.conf import settings
from collections import defaultdict

@transaction.atomic
def update_or_create_articles(df):
    """Actualiza o crea artículos en la base de datos, marca los modificados y aplica descuentos."""

    print(df)
    
    # Obtener el día actual (0 = Lunes, 6 = Domingo)
    hoy = datetime.today().weekday()
    descuentos = DescuentoDiario.objects.filter(dia=hoy)

    for _, row in df.iterrows():
        # Asegurar que los valores sean cadenas antes de aplicar strip()
        code = str(row["Code"]).strip() if not pd.isna(row["Code"]) else ""

        departamento = str(row.get("Departamento", "")).strip() if not pd.isna(row.get("Departamento")) else ""
        secciones = str(row.get("Secciones", "")).strip() if not pd.isna(row.get("Secciones")) else ""
        familia = str(row.get("Familia", "")).strip() if not pd.isna(row.get("Familia")) else ""

        # Normalizar valores numéricos
        stock = int(row["stock"]) if not pd.isna(row["stock"]) else 0
        price = float(row["price"]) if not pd.isna(row["price"]) else 0.0
        discount_price = float(row["discount_price"]) if not pd.isna(row["discount_price"]) else price

        # Buscar si el artículo ya existe
        existing_article = Articulos.objects.filter(code=code).first()
        modificado = False

        if existing_article:
            # Normalizar valores existentes
            existing_stock = int(existing_article.stock) if existing_article.stock is not None else 0
            existing_price = float(existing_article.price) if existing_article.price is not None else 0.0
            existing_discount_price = float(existing_article.discount_price) if existing_article.discount_price is not None else existing_price

            # Comparar valores
            if existing_stock != stock or existing_price != price or existing_discount_price != discount_price:
                modificado = True  # 🔥 Marcarlo como modificado si cambió stock, precio o precio con descuento
        else:
            modificado = True  # 🔥 Si es nuevo, marcar como modificado

        # Aplicar lógica de descuentos
        descuento_aplicado = None
        for descuento in descuentos:
            aplica_por_departamento = descuento.departamento and descuento.departamento == departamento
            aplica_por_secciones = descuento.secciones and descuento.secciones == secciones
            aplica_por_familia = descuento.familia and descuento.familia == familia

            if (descuento.departamento and not descuento.secciones and not descuento.familia and aplica_por_departamento) or \
               (descuento.departamento and descuento.secciones and not descuento.familia and aplica_por_departamento and aplica_por_secciones) or \
               (descuento.departamento and descuento.secciones and descuento.familia and aplica_por_departamento and aplica_por_secciones and aplica_por_familia) or \
               (not descuento.departamento and descuento.secciones and not descuento.familia and aplica_por_secciones) or \
               (not descuento.departamento and not descuento.secciones and descuento.familia and aplica_por_familia):
                descuento_aplicado = descuento
                break  # Solo se aplica un descuento

        # Calcular el precio con descuento si aplica
        if descuento_aplicado:
            discount_price = price * (1 - (descuento_aplicado.porcentaje_descuento / 100))
            modificado = True  # 🔥 Marcar como modificado porque cambió el descuento

        # Actualizar o crear el artículo con el estado de modificación y descuento aplicado
        article, created = Articulos.objects.update_or_create(
            code=code,
            defaults={
                "id_articulo": row["id"],
                "store_id": row["store_id"],
                "ean": row["ean"],
                "name": row["name"],
                "trademark": row["trademark"],
                "description": row["description"],
                "price": price,
                "discount_price": discount_price,
                "stock": stock,
                "sale_type": row["sale_type"],
                "is_available": row["is_available"],
                "departamento": departamento,
                "secciones": secciones,
                "familia": familia,
                "subfamilia": row["SubFamilia"],
                "code": code,
                "modificado": modificado,  # 🔥 Marcar si hubo cambios o es nuevo
            }
        )

        if created:
            print(f"✅ Artículo creado: {article.name} (Marcado como modificado)")
        elif modificado:
            print(f"🔄 Artículo modificado: {article.name} (Stock, precio o descuento cambiado)")


def articulosMoficados():
    return Articulos.objects.filter(modificado=True, price__gt=0)

def marcarArticulosComoNoModificados():
    Articulos.objects.update(modificado=False)



def send_modified_articles():
    """Envía los artículos modificados a la API de Rappi por cada store_id."""
    API_URL = settings.API_URLRAPPI
    API_ENDPOINT = settings.API_ENDPOINTRAPPI
    API_KEY = settings.API_KEYRAPPI

    print(API_URL)
    # Obtener artículos con cambios
    modified_articles = articulosMoficados()

    if not modified_articles.exists():
        print("✅ No hay artículos modificados para enviar.")
        APILogRappi.objects.create(store_id="all", status_code=200, response_text="No hay artículos modificados para enviar.")
        return

    # Agrupar artículos por store_id
    articles_by_store = defaultdict(list)
    for article in modified_articles:
        articles_by_store[article.store_id].append({
            "id": str(article.id_articulo),
            "store_id": str(article.store_id),
            "ean": str(article.ean),
            "name": article.name,
            "description": article.description,
            "trademark": article.trademark,
            "price": float(article.price),
            "discount_price": float(article.discount_price) if article.discount_price else 0.0,
            "stock": int(article.stock),
            "sale_type": article.sale_type,
            "is_available": bool(article.is_available)
        })

    for store_id, records in articles_by_store.items():
        print(f"📤 Enviando {len(records)} artículos para store_id: {store_id}")

        payload = json.dumps({
            "type": "delta",
            "records": records
        })

        headers = {
            "Content-Type": "application/json",
            "api_key": API_KEY
        }

        try:
            conn = http.client.HTTPSConnection(API_URL)
            conn.request("POST", API_ENDPOINT, payload, headers)
            response = conn.getresponse()
            result = response.read().decode("utf-8")

            print(f"📤 Respuesta API para store_id {store_id}: {result}")

            if response.status in [200, 201]:
                # Si la respuesta es correcta, marcar los artículos de esta tienda como no modificados
                Articulos.objects.filter(store_id=store_id, modificado=True).update(modificado=False)
                print(f"✅ Artículos de store_id {store_id} actualizados y marcados como no modificados.")
                APILogRappi.objects.create(store_id=store_id, status_code=response.status, response_text=result)
            else:
                print(f"⚠️ Error en la API para store_id {store_id} (status {response.status}): {result}")
                APILogRappi.objects.create(store_id=store_id, status_code=response.status, response_text=result)

        except Exception as e:
            print(f"🚨 Error al enviar datos a Rappi para store_id {store_id}: {e}")
            APILogRappi.objects.create(store_id=store_id, status_code=500, response_text=str(e))