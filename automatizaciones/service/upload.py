from django.db import transaction
import pandas as pd
from ..models import Articulos, DescuentoDiario, APILogRappi, EnvioLog
import http.client
import json
from datetime import datetime, date
from django.conf import settings
from collections import defaultdict
from django.db.models import Q
import csv
import os
import requests

@transaction.atomic
def update_or_create_articles(df):
    """Actualiza o crea artículos en la base de datos, marca los modificados y aplica descuentos."""

    print(df)
    
    # Obtener el día actual (0 = Lunes, 6 = Domingo)
    hoy = datetime.today().weekday()
    descuentos_dia = DescuentoDiario.objects.filter(dia=hoy)

    for _, row in df.iterrows():
        # Asegurar que los valores sean cadenas antes de aplicar strip()
        code = str(row["Code"]).strip() if not pd.isna(row["Code"]) else ""
        ean = str(row.get("ean", "")).strip() if not pd.isna(row.get("ean")) else ""

        departamento = str(row.get("Departamento", "")).strip() if not pd.isna(row.get("Departamento")) else ""
        secciones = str(row.get("Secciones", "")).strip() if not pd.isna(row.get("Secciones")) else ""
        familia = str(row.get("Familia", "")).strip() if not pd.isna(row.get("Familia")) else ""

        # Normalizar valores numéricos
        stock = int(row["stock"]) if not pd.isna(row["stock"]) else 0
        price = float(row["price"]) if not pd.isna(row["price"]) else 0.0
        discount_price = float(row["discount_price"]) if not pd.isna(row["discount_price"]) else price

        # Buscar si el artículo ya existe
        tarifa = row["tarifa"]
        existing_article = Articulos.objects.filter(code=code, tarifa=tarifa).first()
        modificado = False

        if existing_article:
            # Normalizar valores existentes
            existing_stock = int(existing_article.stock) if existing_article.stock is not None else 0
            existing_price = float(existing_article.price) if existing_article.price is not None else 0.0
            existing_discount_price = float(existing_article.discount_price) if existing_article.discount_price is not None else existing_price

            # Comparar valores
            if existing_stock != stock or existing_price != price or existing_discount_price != discount_price:
                modificado = True  
        else:
            modificado = True 

        # 🔹 Buscar descuento por EAN primero
        descuento_aplicado = DescuentoDiario.objects.filter(
                ean=ean
                ).filter(
                    # Filtra solo descuentos vigentes
                    (Q(fecha_inicio__isnull=True) | Q(fecha_inicio__lte=date.today())) &  
                    (Q(fecha_fin__isnull=True) | Q(fecha_fin__gte=date.today()))
                ).first()

        # 🔹 Si no hay descuento por EAN, buscar por Departamento, Sección o Familia
        if not descuento_aplicado:
            for descuento in descuentos_dia:
                aplica_por_departamento = descuento.departamento and descuento.departamento == departamento
                aplica_por_secciones = descuento.secciones and descuento.secciones == secciones
                aplica_por_familia = descuento.familia and descuento.familia == familia

                if (descuento.departamento and not descuento.secciones and not descuento.familia and aplica_por_departamento) or \
                   (descuento.departamento and descuento.secciones and not descuento.familia and aplica_por_departamento and aplica_por_secciones) or \
                   (descuento.departamento and descuento.secciones and descuento.familia and aplica_por_departamento and aplica_por_secciones and aplica_por_familia) or \
                   (not descuento.departamento and descuento.secciones and not descuento.familia and aplica_por_secciones) or \
                   (not descuento.departamento and not descuento.secciones and descuento.familia and aplica_por_familia):
                    descuento_aplicado = descuento
                    break  
        

        if descuento_aplicado:
            if descuento_aplicado.porcentaje_descuento == 0:
                discount_price = 0
            else:
                discount_price = price * (1 - (descuento_aplicado.porcentaje_descuento / 100))
            modificado = True  #Marcar como modificado porque cambió el descuento
            print(ean)

        # Actualizar o crear el artículo con el estado de modificación y descuento aplicado
        article, created = Articulos.objects.update_or_create(
            code=code,
            tarifa= tarifa,
            defaults={
                "id_articulo": row["id"],
                "store_id": row["store_id"],
                "ean": ean,
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
                "modificado": modificado,
            }
        )

        if created:
            print(f"✅ Artículo creado: {article.name} (Marcado como modificado)")
        elif modificado:
            print(f"🔄 Artículo modificado: {article.name} (Stock, precio o descuento cambiado)")



def articulosMoficados():
    return Articulos.objects.filter(
        Q(store_id="900175315", tarifa=1, modificado=True, price__gt=0) |  # ✅ store_id específico con tarifa = 1
        Q(~Q(store_id="900175315"), modificado=True, price__gt=0)  # ✅ Todos los demás con el mismo filtro excepto tarifa
    )

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

def generar_csv_articulos_modificados():
    """
    Genera un archivo CSV con los artículos modificados y lo guarda en el proyecto.
    """

    directorio = os.path.join(settings.MEDIA_ROOT, "exports")
    os.makedirs(directorio, exist_ok=True)  # Crear directorio si no existe
    ruta_csv = os.path.join(directorio, "articulos_modificados.csv")

    articulos = Articulos.objects.filter(modificado=True,store_id =900175315, tarifa=4, price__gt=0)
    
    with open(ruta_csv, mode="w", encoding="utf-8") as file:
        writer = csv.writer(file)
        
        # Escribir encabezados
        writer.writerow(["SKU", "CANTIDAD", "PRECIO_VENTA", "DESCUENTO_POR_PORCENTAJE", "MAX_SALE", "FEATURED"])
        
        # Escribir datos de los artículos
        
        for articulo in articulos:
            featured = articulo.discount_price < articulo.price and articulo.discount_price > 0
            if articulo.discount_price > 0:
                descuento_porcentaje = round(100 * (1 - (articulo.discount_price / articulo.price)), 2) if featured else 0
                
            else:
                descuento_porcentaje = 0
            
            if featured == True :
                featured = 'TRUE'
            else:
                featured = 'FALSE'
            
            extra = DescuentoDiario.objects.filter(ean=articulo.ean).first()
            max_sale = ''
            if extra:
                if extra.maximo_venta > 0:
                    max_sale = extra.maximo_venta
                else:
                    max_sale = ''
                featured = 'TRUE'

            writer.writerow([
                articulo.ean,        # SKU
                articulo.stock,       # CANTIDAD
                articulo.price,       # PRECIO_VENTA
                descuento_porcentaje, # DESCUENTO_POR_PORCENTAJE
                max_sale,                    # MAX_SALE (ajustar si es necesario)
                featured              # FEATURED (True si tiene descuento)
            ])

    return ruta_csv 


def enviar_csv_a_api():
    """
    Envía el archivo CSV generado a la API externa y guarda un log en la base de datos.
    """
    url = settings.URL_PARZE
    api_key = settings.API_KEY_PARZE

    # Ruta del archivo CSV generado
    ruta_csv = os.path.join(settings.MEDIA_ROOT, "exports", "articulos_modificados.csv")

    # Verificar si el archivo existe
    if not os.path.exists(ruta_csv):
        error_msg = "El archivo CSV no existe. Genera el CSV primero."
        print({"error": error_msg})

        # Guardar en el log
        EnvioLog.objects.create(
            archivo=ruta_csv,
            status="error",
            response_text=error_msg,
            status_code=400  # Código de error indicando que falta el archivo
        )
        return {"error": error_msg}

    # Configurar headers y datos para la petición
    headers = {"Key": api_key}

    try:
        with open(ruta_csv, "rb") as file:
            files = {"file_inventory": file}
            response = requests.post(url, headers=headers, files=files)
            response.raise_for_status()  # Lanza error si el status code no es 2xx
            
            result = response.json()
            print({"success": "Archivo enviado correctamente.", "status_code": response.status_code, "response": result})

            # Guardar en la base de datos el intento exitoso
            EnvioLog.objects.create(
                archivo=ruta_csv,
                status="success",
                status_code=response.status_code,
                response_text=str(result)
            )

            return {"success": "Archivo enviado correctamente.", "status_code": response.status_code, "response": result}

    except requests.exceptions.RequestException as e:
        error_msg = f"Error al enviar el archivo: {str(e)}"
        print({"error": error_msg})

        # Guardar en el log el intento fallido
        EnvioLog.objects.create(
            archivo=ruta_csv,
            status="error",
            status_code=getattr(e.response, "status_code", 500),  # Tomar el código si existe, si no, 500
            response_text=str(e)
        )

        return {"error": error_msg}
