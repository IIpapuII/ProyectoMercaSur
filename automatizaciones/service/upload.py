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
from django.utils.timezone import now
from datetime import time, timedelta


@transaction.atomic
def update_or_create_articles(df):
    """Actualiza o crea artículos en la base de datos, marca los modificados y aplica descuentos."""

    print(df)

    # Obtener el día actual (0 = Lunes, 6 = Domingo)
    hoy = datetime.today().weekday()
    descuentos_dia = DescuentoDiario.objects.filter(activo=True)

    for _, row in df.iterrows():
        # Asegurar que los valores sean cadenas antes de aplicar strip()
        code = str(row["Code"]).strip() if not pd.isna(row["Code"]) else ""
        ean = str(row.get("ean", "")).strip() if not pd.isna(row.get("ean")) else ""

        departamento = str(row.get("Departamento", "")).strip() if not pd.isna(row.get("Departamento")) else ""
        secciones = str(row.get("Secciones", "")).strip() if not pd.isna(row.get("Secciones")) else ""
        familia = str(row.get("Familia", "")).strip() if not pd.isna(row.get("Familia")) else ""
        trademark = str(row.get("trademark", "")).strip() if not pd.isna(row.get("trademark")) else ""

        # Normalizar valores numéricos
        stock = int(row["stock"]) if not pd.isna(row["stock"]) else 0
        price = float(row["price"]) if not pd.isna(row["price"]) else 0.0
        discount_price = float(row["discount_price"]) if not pd.isna(row["discount_price"]) else price
        is_featured = False  # Nuevo campo para marcar productos destacados

        # Buscar si el artículo ya existe
        tarifa = row["tarifa"]
        existing_article = Articulos.objects.filter(code=code).first()
        modificado = False

        if existing_article:
            # Normalizar valores existentes
            existing_stock = int(existing_article.stock) if existing_article.stock is not None else 0
            existing_price = float(existing_article.price) if existing_article.price is not None else 0.0
            existing_discount_price = float(existing_article.discount_price) if existing_article.discount_price is not None else existing_price
            existing_featured = existing_article.is_featured

            # 🔹 Comparar valores antes de marcar como modificado
            cambios_detectados = (
                existing_stock != stock or
                existing_price != price or
                existing_discount_price != discount_price or
                existing_featured != is_featured
            )

            modificado = cambios_detectados  

        else:
            modificado = True  

        # 🔹 Buscar descuento vigente por EAN
        descuento_aplicado = DescuentoDiario.objects.filter(
            ean=ean,
            activo=True
        ).first()
        # 🔹 Si no hay descuento por EAN, buscar por Departamento, Sección o Familia
        if not descuento_aplicado:
            for descuento in descuentos_dia:
                aplica_por_departamento = descuento.departamento and descuento.departamento == departamento
                aplica_por_secciones = descuento.secciones and descuento.secciones == secciones
                aplica_por_familia = descuento.familia and descuento.familia == familia
                aplica_por_marca = descuento.Trademark and descuento.Trademark ==  trademark# ✅ Verifica la marca

                if (descuento.departamento and not descuento.secciones and not descuento.familia and not descuento.Trademark and aplica_por_departamento) or \
                    (descuento.departamento and descuento.secciones and not descuento.familia and not descuento.Trademark and aplica_por_departamento and aplica_por_secciones) or \
                    (descuento.departamento and descuento.secciones and descuento.familia and not descuento.Trademark and aplica_por_departamento and aplica_por_secciones and aplica_por_familia) or \
                    (not descuento.departamento and descuento.secciones and not descuento.familia and not descuento.Trademark and aplica_por_secciones) or \
                    (not descuento.departamento and not descuento.secciones and descuento.familia and not descuento.Trademark and aplica_por_familia) or \
                    (not descuento.departamento and not descuento.secciones and not descuento.familia and descuento.Trademark and aplica_por_marca) or \
                    (descuento.departamento and descuento.Trademark and not descuento.secciones and not descuento.familia and aplica_por_departamento and aplica_por_marca) or \
                    (descuento.secciones and descuento.Trademark and not descuento.departamento and not descuento.familia and aplica_por_secciones and aplica_por_marca) or \
                    (descuento.familia and descuento.Trademark and not descuento.departamento and not descuento.secciones and aplica_por_familia and aplica_por_marca) or \
                    (descuento.departamento and descuento.secciones and descuento.Trademark and not descuento.familia and aplica_por_departamento and aplica_por_secciones and aplica_por_marca) or \
                    (descuento.departamento and descuento.secciones and descuento.familia and descuento.Trademark and aplica_por_departamento and aplica_por_secciones and aplica_por_familia and aplica_por_marca): 

                    descuento_aplicado = descuento
                    break 
        # 🔹 Aplicar descuento solo si hay cambios
        nuevo_discount_price = discount_price  # Mantener el precio original

        if descuento_aplicado:
            if descuento_aplicado.porcentaje_descuento == 0:
                is_featured = True  # Si el descuento es 0%, marcar como destacado
            else:
                nuevo_discount_price = price * (1 - (descuento_aplicado.porcentaje_descuento / 100))

            
            if nuevo_discount_price != discount_price or is_featured != existing_featured:
                modificado = True  # Solo marcar como modificado si realmente hay un cambio
            
            print(f"🔻 Descuento aplicado a {ean}")

        # 🔹 Si el artículo tenía descuento pero ya no aplica, restablecer precio solo si venía de un descuento en DescuentoDiario
        elif existing_article and existing_article.discount_price < existing_article.price:
            # Verificar si el artículo realmente tenía un descuento en DescuentoDiario antes de eliminarlo
            descuento_anterior = DescuentoDiario.objects.filter(ean=ean).exists()
            
            if descuento_anterior and not descuento_aplicado:
                nuevo_discount_price = 0  # Restablecer precio original
                is_featured = False
                if existing_article.discount_price != nuevo_discount_price or existing_article.is_featured != is_featured:
                    modificado = True  
                print(f"🔺 Descuento eliminado para {ean}")

        # 🔹 Crear o actualizar el artículo solo si hay cambios
        article, created = Articulos.objects.update_or_create(
            code=code,
            defaults={
                "id_articulo": row["id"],
                "store_id": row["store_id"],
                "ean": ean,
                "name": row["name"],
                "trademark": row["trademark"],
                "description": row["description"],
                "price": price,
                "discount_price": nuevo_discount_price,
                "stock": stock,
                "sale_type": row["sale_type"],
                "is_available": row["is_available"],
                "departamento": departamento,
                "secciones": secciones,
                "familia": familia,
                "subfamilia": row["SubFamilia"],
                "code": code,
                "modificado": modificado,
                "tarifa": tarifa,
                "is_featured": is_featured,  # Guardar el estado de destacado
            }
        )

        if created:
            print(f"✅ Artículo creado: {article.name} (Marcado como modificado)")
        elif modificado:
            print(f"🔄 Modificaciones en {article.name} ({article.code}):")
            if existing_article:
                if existing_article.stock != stock:
                    print(f" - stock: {existing_article.stock} -> {stock}")
                if existing_article.price != price:
                    print(f" - price: {existing_article.price} -> {price}")
                if existing_article.discount_price != nuevo_discount_price:
                    print(f" - discount_price: {existing_article.discount_price} -> {nuevo_discount_price}")
                if existing_article.is_featured != is_featured:
                    print(f" - is_featured: {existing_article.is_featured} -> {is_featured}")




def articulosMoficados():
    return Articulos.objects.filter(
        Q(store_id="900175315", tarifa=1, modificado=True, price__gt=0) |  # ✅ store_id específico con tarifa = 1
        Q(~Q(store_id="900175315"), modificado=True, price__gt=0)  # ✅ Todos los demás con el mismo filtro excepto tarifa
    )

def articulosModificadosTotal():
        return Articulos.objects.filter(
        Q(store_id="900175315", tarifa=1, price__gt=0) |  # ✅ store_id específico con tarifa = 1
        Q(~Q(store_id="900175315"), price__gt=0)  # ✅ Todos los demás con el mismo filtro excepto tarifa
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
            "trademark": article.trademark,
            "description": article.description,
            "price": float(article.price),
            "discount_price": float(article.discount_price) if article.discount_price else 0.0,
            "stock": int(article.stock),
            "sale_type": article.sale_type,
            "is_available": bool(article.is_available),
            "image_url":""
        })

    for store_id, records in articles_by_store.items():
        print(f"📤 Enviando {len(records)} artículos para store_id: {store_id}")

        payload = json.dumps({
            "type": "delta",
            "records": records
        }, indent=4, ensure_ascii=False)
        file = os.path.join(settings.MEDIA_ROOT, "exports")
        filename = os.path.join(file, f"payload_{store_id}.json" )
        with open(filename, "w", encoding="utf-8") as f:
            f.write(payload)
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

def send_modified_articles_total():
    """Envía los artículos modificados a la API de Rappi por cada store_id."""
    API_URL = settings.API_URLRAPPI
    API_ENDPOINT = settings.API_ENDPOINTRAPPI
    API_KEY = settings.API_KEYRAPPI

    print(API_URL)
    # Obtener artículos con cambios
    modified_articles = articulosModificadosTotal()

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
            "trademark": article.trademark,
            "description": article.description,
            "price": float(article.price),
            "discount_price": float(article.discount_price) if article.discount_price else 0.0,
            "stock": int(article.stock),
            "sale_type": article.sale_type,
            "is_available": bool(article.is_available),
            "image_url":""
        })

    for store_id, records in articles_by_store.items():
        print(f"📤 Enviando {len(records)} artículos para store_id: {store_id}")

        payload = json.dumps({
            "type": "full",
            "records": records
        },indent=4, ensure_ascii=False)
        file = os.path.join(settings.MEDIA_ROOT, "exports")
        filename = os.path.join(file, f"payload_{store_id}.json" )
        with open(filename, "w", encoding="utf-8") as f:
            f.write(payload)
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

    # Filtrar solo artículos modificados con ciertas condiciones
    articulos = Articulos.objects.filter(modificado=True, store_id=900175315, tarifa=4, price__gt=0)
    ahora = datetime.now()
    hora_actual = ahora.time()
    # Obtener el día actual (0 = Lunes, 6 = Domingo)
    if hora_actual > time(17,30):
        hoy = (datetime.today().weekday() + 1) % 7
        fecha_hoy = date.today() + timedelta(days=1)
    else:
        hoy = datetime.today().weekday()
        fecha_hoy = date.today()

    with open(ruta_csv, mode="w", encoding="utf-8", newline="") as file:
        writer = csv.writer(file)
        
        # Escribir encabezados
        writer.writerow(["SKU", "CANTIDAD", "PRECIO_VENTA", "DESCUENTO_POR_PORCENTAJE", "MAX_SALE", "FEATURED"])
        
        # Procesar cada artículo
        for articulo in articulos:
            descuento = None  # Inicializar variable de descuento como None

            # 🔹 Buscar descuento por EAN, pero solo si está vigente
            descuento = DescuentoDiario.objects.filter(
                ean=articulo.ean,
                activo=True,
            ).filter(
                Q(dia=hoy) |  
                (Q(fecha_inicio__lte=fecha_hoy) & Q(fecha_fin__gte=fecha_hoy))  
            ).first()

            # 🔹 Si no hay descuento por EAN, buscar por Departamento, Sección o Familia
            if not descuento:
                descuentos_dia = DescuentoDiario.objects.filter(
                    dia=hoy,
                    activo=True,
                )

                for d in descuentos_dia:
                    if (d.departamento and d.departamento == articulo.departamento) or \
                       (d.secciones and d.secciones == articulo.secciones) or \
                       (d.familia and d.familia == articulo.familia)or \
                        (d.Trademark and d.Trademark == articulo.trademark):
                        descuento = d
                        break  

            # 🔹 Determinar si el descuento está activo
            descuento_activo = (
                descuento and (
                    (descuento.dia == hoy) or 
                    (descuento.fecha_inicio is None and descuento.fecha_fin is None) or 
                    (descuento.fecha_inicio <= fecha_hoy and descuento.fecha_fin >= fecha_hoy)
                )
            )
            # 🔹 Si el descuento NO está activo, forzar `featured = FALSE` y `max_sale = ""`
            featured = "TRUE" if descuento_activo else "FALSE"
            max_sale = descuento.maximo_venta if descuento_activo and descuento.maximo_venta > 0 else ""

            # 🔹 Calcular porcentaje de descuento y determinar precio de venta
            if articulo.discount_price > 0 and articulo.discount_price < articulo.price:
                precio_venta = articulo.discount_price
                descuento_porcentaje = round(100 * (1 - (articulo.discount_price / articulo.price)), 2)
            else:
                precio_venta = articulo.price
                descuento_porcentaje = 0  # No hay descuento

            # 🔹 Escribir datos en el CSV
            writer.writerow([
                articulo.ean,        # SKU
                articulo.stock,      # CANTIDAD
                precio_venta,        # PRECIO_VENTA (discount_price si tiene, sino price)
                descuento_porcentaje, # DESCUENTO_POR_PORCENTAJE
                max_sale,            # MAX_SALE (vacío si el descuento no está activo)
                featured             # FEATURED (TRUE solo si el descuento está activo)
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


def actualizar_descuentos():
    """Desactiva descuentos vencidos y activa los del día siguiente en el momento correcto."""
    ahora = datetime.now()
    fecha_hoy = ahora.date()
    hora_actual = ahora.time()

    # Solo ejecutamos la lógica si la hora es 5:30 PM o después
    if hora_actual < time(17, 30):
        print("No ingreso al proceso")
        return

    # 1. Desactivar descuentos vencidos (los que ya pasaron su fecha_fin)
    descuentos_vencidos = DescuentoDiario.objects.filter(
        activo=True,
        fecha_fin__lt=fecha_hoy  # Desactiva los descuentos que terminaron antes de hoy
    )
    count_vencidos = descuentos_vencidos.update(activo=False)
    print(f"Desactivados {count_vencidos} descuentos vencidos hasta {fecha_hoy}.")

    # 2. Desactivar descuentos incorrectamente activos (no corresponden al día actual)
    dia_hoy = fecha_hoy.weekday()  # 0 = Lunes, 6 = Domingo
    descuentos_mal_activados = DescuentoDiario.objects.filter(
        activo=True,
        dia__lt=dia_hoy  # Excluimos los que sí son del día correcto
    ).exclude(
        fecha_inicio__lte=fecha_hoy,
        fecha_fin__gte=fecha_hoy
    )
    count_mal_activados = descuentos_mal_activados.update(activo=False)
    print(f"Desactivados {count_mal_activados} descuentos que estaban activos en días incorrectos.")

    # 3. Activar descuentos con fecha de inicio mañana
    fecha_manana = fecha_hoy + timedelta(days=1)
    descuentos_fecha_manana = DescuentoDiario.objects.filter(
        activo=False,
        fecha_inicio=fecha_manana
    )
    count_fecha_manana = descuentos_fecha_manana.update(activo=True)
    print(f"Activados {count_fecha_manana} descuentos con fecha de inicio {fecha_manana}.")

    # 4. Activar descuentos del próximo día con descuentos
    dia_siguiente = (dia_hoy + 1) % 7  # Día inmediato siguiente

    # Buscar el próximo día con descuentos
    while not DescuentoDiario.objects.filter(dia=dia_siguiente).exists():
        dia_siguiente = (dia_siguiente + 1) % 7  # Buscar el próximo día con descuentos

    # Solo activar si estamos en el día anterior al próximo día con descuentos
    if dia_siguiente == (dia_hoy + 1) % 7:
        descuentos_dia_siguiente = DescuentoDiario.objects.filter(
            activo=False,
            dia=dia_siguiente
        )
        count_dia_siguiente = descuentos_dia_siguiente.update(activo=True)
        print(f"Activados {count_dia_siguiente} descuentos del día {dia_siguiente}.")
    else:
        print(f"No se activan descuentos. Esperando hasta el día anterior al día {dia_siguiente}.")

    # 5. Mantener activos los descuentos que aún están dentro de su rango de fechas
    descuentos_activos_validos = DescuentoDiario.objects.filter(
        activo=True,
        fecha_inicio__lte=fecha_hoy,
        fecha_fin__gte=fecha_hoy
    )
    count_activos_validos = descuentos_activos_validos.count()
    print(f"{count_activos_validos} descuentos permanecen activos porque están dentro de su rango de fechas.")

    if hora_actual > time(17, 30):
        descuentos_activos_validos = DescuentoDiario.objects.filter(
           activo=True,
           fecha_fin = fecha_hoy 
        )
        descuentos_hoy_validos = DescuentoDiario.objects.filter(
            activo=True,
            dia=dia_hoy
        )
        count_hoy_validos = descuentos_hoy_validos.update(activo=False)
        count_activos_validos = descuentos_activos_validos.update(activo=False)
        print("Se desactivan Descuentos")