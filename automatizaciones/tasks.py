from celery import shared_task
from .service.upload import update_or_create_articles, send_modified_articles
from appMercaSur.conect import conectar_sql_server, ejecutar_consulta
from .models import SQLQuery
import pandas as pd
import pyodbc
from django.conf import settings

@shared_task
def procesar_articulos_task():
    """Tarea programada para actualizar y enviar artículos modificados."""
    try:
        print("🔄 Iniciando tarea de procesamiento de artículos...")
        
        conexion = conectar_sql_server()

        # 2️⃣ Obtener la consulta desde el modelo SQLQuery
        consulta = SQLQuery.objects.filter(pk=2).first()
        if not consulta:
            print("⚠️ No hay consultas activas.")
            return

        # 3️⃣ Ejecutar la consulta
        df = ejecutar_consulta(conexion, consulta.consulta)
        if df is None:
            print("⚠️ No se pudo ejecutar la consulta.")
            return

        # 5️⃣ Actualizar o crear artículos
        update_or_create_articles(df)

        # 6️⃣ Enviar artículos modificados a Rappi
        send_modified_articles()

        print("✅ Proceso de artículos completado.")

    except Exception as e:
        print(f"🚨 Error en procesar_articulos_task: {e}")
