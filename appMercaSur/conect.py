import pyodbc
import warnings
from django.conf import settings
# Configuración de conexión - MODIFICAR ESTOS VALORES
import pandas as pd

def conectar_sql_server():
    try:
        # Cadena de conexión
        connection_string = f'''
            DRIVER={settings.DRIVERICG};
            SERVER={settings.SERVERICG};
            DATABASE={settings.DBICG};
            UID={settings.USERICG};
            PWD={settings.PASSICG};
            TrustServerCertificate=yes;
            Encrypt=no;
        '''
        
        # Establecer conexión
        conexion = pyodbc.connect(connection_string)
        print("¡Conexión exitosa a SQL Server!")
        
        return conexion
    
    except pyodbc.Error as e:
        print(f"Error de conexión: {str(e)}")
        return None

def ejecutar_consulta(conexion, consulta):
    """Ejecuta la consulta en SQL Server y retorna los resultados en un DataFrame."""
    try:
        cursor = conexion.cursor()
        cursor.execute(consulta)
        columnas = [column[0] for column in cursor.description] 
        datos = cursor.fetchall() 

        df = pd.DataFrame.from_records(datos, columns=columnas)  
        return df

    except pyodbc.Error as e:
        print(f"⚠️ Error en consulta: {str(e)}")
        return None

def ejecutar_consulta_data(conexion, consulta):
    """Ejecuta la consulta en SQL Server y retorna los resultados en un DataFrame."""
    try:
        cursor = conexion.cursor()
        cursor.execute(consulta)
        datos = cursor.fetchall() 
        return datos

    except pyodbc.Error as e:
        print(f"⚠️ Error en consulta: {str(e)}")
        return None

def ejecutar_consulta_data_auto(conexion, consulta_sql):
    """Ejecuta la consulta en SQL Server y retorna los resultados."""
    if not consulta_sql:
        print("⚠️ Consulta SQL vacía, no se ejecutará.")
        return None
    if not conexion:
         print("❌ No hay conexión a BD para ejecutar la consulta.")
         raise ConnectionError("Conexión a base de datos no disponible.")
    try:
        cursor = conexion.cursor()
        print(f"🚀 Ejecutando consulta: {consulta_sql[:100]}...")
        cursor.execute(consulta_sql)
        # Obtener nombres de columnas para devolver lista de diccionarios
        columns = [column[0] for column in cursor.description]
        datos = [dict(zip(columns, row)) for row in cursor.fetchall()]
        print(f"✔️ Consulta ejecutada, {len(datos)} filas obtenidas.")
        return datos
    except pyodbc.Error as e:
        print(f"⚠️ Error en consulta pyodbc: {str(e)}")
        # Podrías querer devolver None o lanzar una excepción más específica
        raise # Re-lanza para que Celery lo capture como error de consulta
    finally:
        # Es importante cerrar el cursor si no usas 'with'
        if 'cursor' in locals() and cursor:
            cursor.close()

def ejecutar_consulta_simple(conexion, sql: str, params: tuple | list | None = None) -> int | None:
    """
    Ejecuta una sentencia SQL (DDL/DML) y, si corresponde, devuelve el número de filas afectadas.

    :param conexion: Objeto de conexión DB-API (p.ej. pyodbc.Connection, psycopg2.Connection).
    :param sql: Cadena con la consulta SQL (ALTER, UPDATE, DELETE, INSERT...).
    :param params: Secuencia de parámetros para la consulta (tupla o lista), o None.
    :return: Número de filas afectadas (rowcount) para DML, o None para DDL.
    """
    cursor = conexion.cursor()
    try:
        if params:
            cursor.execute(sql, params)
        else:
            cursor.execute(sql)

        # Si la conexión no está en autocommit, confirmamos cambios
        try:
            conexion.commit()
        except AttributeError:
            # Algunos drivers (p.ej. sqlite en autocommit) no exponen commit()
            pass

        # Para DML devuelve rowcount; para DDL típicamente -1 o 0
        return cursor.rowcount if cursor.rowcount >= 0 else None

    except Exception as e:
        # Puedes personalizar el manejo de errores o relanzar uno más explícito
        raise RuntimeError(f"Error al ejecutar la consulta: {e}") from e

    finally:
        cursor.close()

