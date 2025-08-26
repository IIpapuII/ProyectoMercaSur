from celery import shared_task, states
from celery.exceptions import Ignore
from django.db import transaction
from django.template import TemplateSyntaxError
from django.utils import timezone

from automatizaciones.service.rappi_missing import log_missing_product
from automatizaciones.service.rappi_update_state import RappiError, update_inventory_one_by_one
from .service.upload import *
from appMercaSur.conect import conectar_sql_server, ejecutar_consulta, ejecutar_consulta_data_auto
from .models import SQLQuery
import pandas as pd
import pyodbc
from django.conf import settings
from .models import CorreoEnviado
from .utils import enviar_correo_renderizado
from .service.rappi_auth import get_rappi_token

@shared_task
def procesar_articulos_task():
    """Tarea programada para actualizar y enviar artículos modificados."""
    try:
        print("Iniciando tarea de procesamiento de artículos...")
        
        conexion = conectar_sql_server()

        #  Obtener la consulta desde el modelo SQLQuery
        consulta = SQLQuery.objects.filter(pk=2).first()
        if not consulta:
            print("No hay consultas activas.")
            return

        #  Ejecutar la consulta
        df = ejecutar_consulta(conexion, consulta.consulta)
        if df is None:
            print("No se pudo ejecutar la consulta.")
            return

        # 5️⃣ Actualizar o crear artículos
        update_or_create_articles(df,'Rappi')

        #  Enviar artículos modificados a Rappi
        send_modified_articles()

        print("Proceso de artículos completado.")

    except Exception as e:
        print(f"Error en procesar_articulos_task: {e}")
        raise

@shared_task()
def procesar_articulos_task_total():
    """Tarea programada para actualizar y enviar artículos modificados."""
    try:
        print("Iniciando tarea de procesamiento de artículos...")
        
        conexion = conectar_sql_server()

        #  Obtener la consulta desde el modelo SQLQuery
        consulta = SQLQuery.objects.filter(pk=2).first()
        if not consulta:
            print("No hay consultas activas.")
            return

        #  Ejecutar la consulta
        df = ejecutar_consulta(conexion, consulta.consulta)
        if df is None:
            print("No se pudo ejecutar la consulta.")
            return

        # 5️⃣ Actualizar o crear artículos
        update_or_create_articles(df,'Rappi')

        #  Enviar artículos modificados a Rappi
        send_modified_articles_total()

        print("Proceso de artículos completado.")

    except Exception as e:
        print(f"Error en procesar_articulos_task: {e}")
        raise

@shared_task
def procesar_articulos_parze_task():
    """Tarea programada para actualizar y enviar artículos modificados."""
    try:
        print("Iniciando tarea de procesamiento de artículos...")
        
        conexion = conectar_sql_server()

        #  Obtener la consulta desde el modelo SQLQuery
        consulta = SQLQuery.objects.filter(pk=2).first()
        if not consulta:
            print("No hay consultas activas.")
            return

        #  Ejecutar la consulta
        df = ejecutar_consulta(conexion, consulta.consulta)
        if df is None:
            print("No se pudo ejecutar la consulta.")
            return

        # 5️⃣ Actualizar o crear artículos
        update_or_create_articles(df, 'Parze')

        #  Enviar artículos modificados a Rappi
        generar_csv_articulos_modificados()
        enviar_csv_a_api()
        print("Enviado")
        marcarArticulosComoNoModificados()
        print("Proceso de artículos completado.")

    except Exception as e:
        print(f"Error en procesar_articulos_task: {e}")
        raise

@shared_task
def actualizar_descuentos_task():
    """Tarea programada para actualizar los descuentos diarios."""
    try:
        print("Iniciando tarea de actualización de descuentos...")
        
        actualizar_descuentos()
        print("Iniciando tarea de procesamiento de artículos...")
        
        conexion = conectar_sql_server()

        #  Obtener la consulta desde el modelo SQLQuery
        consulta = SQLQuery.objects.filter(pk=2).first()
        if not consulta:
            print("No hay consultas activas.")
            return

        #  Ejecutar la consulta
        df = ejecutar_consulta(conexion, consulta.consulta)
        if df is None:
            print("No se pudo ejecutar la consulta.")
            return


        print(f"Procesando artículos para canal: Parze")
        update_or_create_articles(df, canal="Parze")
        generar_csv_articulos_modificados()
        enviar_csv_a_api()
        send_modified_articles()
        print("Proceso completado para ambos canales.")
        
        procesar_articulos_task_total()
        return "proceso exitoso"

    except Exception as e:
        print(f"Error en actualizar_descuentos_task: {e}")
        raise


# --- Helper para actualizar estado ---
# (Sin cambios respecto al anterior)
def actualizar_estado_envio(envio_id, nuevo_estado, error_msg=None, task_id=None, fecha_procesamiento=None, fecha_envio=None):
    try:
        # Usar transaction.atomic para asegurar la atomicidad de la lectura y escritura
        with transaction.atomic():
            # Obtener con select_for_update para bloquear la fila durante la actualización
            envio = CorreoEnviado.objects.select_for_update().get(pk=envio_id)
            update_fields = ['estado']
            envio.estado = nuevo_estado

            if error_msg is not None:
                envio.error_detalle = str(error_msg)[:2000]
                update_fields.append('error_detalle')
            elif nuevo_estado not in ['ERROR_QUERY', 'ERROR_TEMPLATE', 'ERROR_ENVIO', 'ERROR_CONFIG']:
                 if envio.error_detalle:
                     envio.error_detalle = None
                     update_fields.append('error_detalle')

            if task_id is not None and envio.task_id != task_id:
                 envio.task_id = task_id
                 update_fields.append('task_id')
            if fecha_procesamiento and envio.fecha_procesamiento != fecha_procesamiento:
                 envio.fecha_procesamiento = fecha_procesamiento
                 update_fields.append('fecha_procesamiento')
            if fecha_envio and envio.fecha_envio != fecha_envio:
                 envio.fecha_envio = fecha_envio
                 update_fields.append('fecha_envio')

            if update_fields:
                envio.save(update_fields=update_fields)
                print(f"Estado de Envio ID {envio_id} actualizado a {nuevo_estado}.")

    except CorreoEnviado.DoesNotExist:
         print(f"Error al actualizar estado: Envio ID {envio_id} no encontrado.")
         raise
    except Exception as e:
         # Captura errores de bloqueo de base de datos u otros problemas
         print(f"Error inesperado al actualizar estado para Envio ID {envio_id}: {e}")
         # Podrías querer reintentar la tarea aquí si es un error de bloqueo temporal
         raise

# Nombre de la tarea
TASK_NAME = 'automatizaciones.tasks.procesar_y_enviar_correo_task' 

# --- Tarea Principal (Modificada) ---
@shared_task(bind=True, name=TASK_NAME, max_retries=2, default_retry_delay=180)
def procesar_y_enviar_correo_task(self, envio_id):
    task_id = self.request.id
    print(f"Iniciando tarea {task_id} para EnvioProgramado ID: {envio_id}")
    envio = None
    conexion_db = None # Variable para la conexión

    try:
        envio = CorreoEnviado.objects.select_related('consulta').get(pk=envio_id)

        allowed_initial_states = ['ACTIVO', 'INACTIVO', 'PENDIENTE', 'PROGRAMADO']
        if envio.estado not in allowed_initial_states:
             print(f"Tarea {task_id}: Envío {envio_id} estado inválido ({envio.estado}). Omitiendo.")
             raise Ignore()

        actualizar_estado_envio(envio_id, 'PROCESANDO', task_id=task_id, fecha_procesamiento=timezone.now())

        datos_consulta = {}
        contexto_final = {'fecha_actual': timezone.now()} # Contexto base

        # --- 1. Ejecutar Consulta (si aplica) ---
        if envio.consulta:
            print(f"Tarea {task_id}: Preparando para ejecutar consulta ID: {envio.consulta.pk}")
            if not SQLQuery: raise ImportError("Modelo SQLQuery no disponible.")

            try:
                # --- Obtener conexión ---
                conexion_db = conectar_sql_server() # Llama a tu función para conectar

                # --- Obtener el SQL de tu modelo ---
                consulta_sql_string = envio.consulta.consulta 
                if not consulta_sql_string:
                    raise ValueError(f"La consulta SQL en SQLQuery ID {envio.consulta.pk} está vacía.")

                # --- Ejecutar usando tu función ---
                datos_crudos = ejecutar_consulta_data_auto(conexion_db, consulta_sql_string)

                # Prepara el contexto para la plantilla
                contexto_final['resultados'] = datos_crudos # Añade los resultados al contexto
                print(f"Tarea {task_id}: Consulta ejecutada.")

            except (ImportError, AttributeError, ValueError, ConnectionError, pyodbc.Error) as e_query:
                 print(f"Error Tarea {task_id}: Fallo relacionado a consulta para envío {envio_id}. Error: {e_query}")
                 actualizar_estado_envio(envio_id, 'ERROR_QUERY', error_msg=e_query)
                 raise Ignore() # No reintentar
            except Exception as e_inesperado_query:
                 print(f"Error Tarea {task_id}: Error inesperado durante consulta {envio_id}. Error: {e_inesperado_query}")
                 actualizar_estado_envio(envio_id, 'ERROR_QUERY', error_msg=e_inesperado_query)
                 raise Ignore() # No reintentar
            finally:
                if conexion_db:
                    try:
                        if not conexion_db.closed:  # 👈 Evita cerrar si ya está cerrada
                            conexion_db.close()
                            print(f"Tarea {task_id}: Conexión a BD cerrada en finally.")
                    except Exception as e_close:
                        print(f"Tarea {task_id}: Error al cerrar conexión en finally: {e_close}")
        else:
             print(f"Tarea {task_id}: No hay consulta SQL asociada. Correo informativo.")
             # contexto_final ya tiene 'fecha_actual'

        # --- 2. Enviar Correo usando tu función ---
        # (Renderizado y envío ahora dentro de enviar_correo_renderizado)
        print(f"Tarea {task_id}: Llamando a enviar_correo_renderizado para envío {envio_id}")

        try:
            envio_exitoso = enviar_correo_renderizado(
                asunto=envio.asunto,
                destinatarios=envio.destinatarios, # La función interna normaliza
                template_html_string=envio.cuerpo_html,
                contexto=contexto_final
            )

            if envio_exitoso:
                print(f"Tarea {task_id}: Correo {envio_id} marcado como enviado por la función helper.")
                final_state = 'ACTIVO' if envio.activo else 'INACTIVO'
                return f"Enviado: {envio_id}"
            else:
                 # Si la función devuelve False pero no lanza excepción (ej. no destinatarios)
                 raise Exception("La función enviar_correo_renderizado devolvió False.")

        except (TemplateSyntaxError, ValueError) as e_render:
             # Error específico de plantilla capturado desde la función helper
             print(f"Error Tarea {task_id}: Error de plantilla detectado para envío {envio_id}. Error: {e_render}")
             raise Ignore() # No reintentar
        except Exception as e_envio:
             # Captura errores de envío (SMTP, etc.) o el Exception del helper
             print(f"Error Tarea {task_id}: Fallo el envío para {envio_id} (posiblemente desde helper). Error: {e_envio}")
             # Proceder a lógica de reintento...
             raise # Re-lanza la excepción para que el bloque except general la maneje

    except Ignore:
         print(f"Tarea {task_id}: Ignorada para envío {envio_id}.")
         return f"Ignorado: {envio_id}"

    except Exception as e_general:
        # Captura errores generales o los re-lanzados por el envío
        print(f"Error Tarea {task_id}: Fallo general procesando {envio_id}. Error: {e_general}")
        try:
            print(f"Tarea {task_id}: Reintento {self.request.retries + 1}/{self.max_retries} para envío {envio_id}")
            original_state = 'ACTIVO' if envio and envio.activo else 'INACTIVO'

            raise self.retry(exc=e_general)
        except self.MaxRetriesExceededError:
            print(f"Tarea {task_id}: Máximos reintentos alcanzados para envío {envio_id}. Marcando como ERROR_ENVIO.")
            return f"Error final envío: {envio_id}"
        except Exception as e_retry:
             print(f"Tarea {task_id}: Error inesperado durante reintento para {envio_id}. Error: {e_retry}")
             return f"Error en reintento: {envio_id}"
    finally:
        # Asegurarse de cerrar la conexión si sigue abierta por alguna razón
        if conexion_db:
            try:
                conexion_db.close()
                print(f"Tarea {task_id}: Conexión a BD cerrada en finally.")
            except Exception as e_close:
                print(f"Tarea {task_id}: Error al cerrar conexión en finally: {e_close}")


@shared_task
def rappi_active_product():
    """Tarea programada para actualizar y enviar artículos modificados."""
    LOCAL_TO_NAME = {
        "900175315": "Mercasur, Caldas",
        "900175197": "Mercasur, Soto Mayor",
        "900175196": "Mercasur, Cabecera",
        "900174620": "Mercasur, Centro",
    }

    # nombre -> id interno de Rappi (del JSON que pasaste)
    NAME_TO_RAPPI = {
        "Mercasur, Centro": 21128,
        "Mercasur, Cabecera": 21243,
        "Mercasur, Soto Mayor": 21244,
        "Mercasur, Caldas": 21261,
    }

    server = settings.RAPPI_URL_BASE
    token = get_rappi_token()

    qs = Articulos.objects.all().order_by("store_id")

    results = []
    for art in qs:
        print("Actualizando artículo:", art.ean, "en tienda local", art.store_id)
        try:
            res = update_inventory_one_by_one(
                server=server,
                token=token,
                articulo=art,
                local_to_name=LOCAL_TO_NAME,
                name_to_rappi=NAME_TO_RAPPI,
            )
            results.append({"ean": art.ean, "store_id": art.store_id, "ok": True, "detail": res})
        except RappiError as e:
            err = str(e)
            if "No encontré IDs" in err or "no devolvió ni productId ni listingId" in err:
                store_name = LOCAL_TO_NAME.get(str(art.store_id).strip())
                rappi_store_id = NAME_TO_RAPPI.get(store_name)
                # si tu update_inventory_one_by_one devuelve 'lookups' en el dict de error, pásalo aquí
                log_missing_product(
                    articulo=art,
                    store_name=store_name,
                    rappi_store_id=rappi_store_id,
                    error=err,
                    lookups_debug=None,  # pon aquí el detalle si lo tienes
                )
            results.append({"ean": art.ean, "store_id": art.store_id, "ok": False, "error": str(e)})