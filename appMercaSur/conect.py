import pyodbc
import warnings
from django.conf import settings
# Configuración de conexión - MODIFICAR ESTOS VALORES

def conectar_sql_server():
    try:
        # Cadena de conexión
        connection_string = f'''
            DRIVER={settings.DRIVERICG};
            SERVER={settings.SERVERICG};
            DATABASE={settings.DBICG};
            UID={settings.USERICG};
            PWD={settings.PASSICG};
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