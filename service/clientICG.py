from appMercaSur.conect import conectar_sql_server, ejecutar_consulta_data
from clientes.models import RegistroCliente, ZonaPermitida
from automatizaciones.models import SQLQuery
from geopy.distance import geodesic
from datetime import datetime
from clientes.correo import enviar_correo
from clientes.utils import generar_nuevo_codcliente, calcular_edad, bool_a_tf

def getClienteICG(numero_documento):
    """
    Obtiene información del cliente desde la base de datos SQL Server.
    Args:
        numero_documento: El número de documento del cliente a consultar.
    Returns:
        list: Lista de datos del cliente.
    """
    try:
        conexion = conectar_sql_server()
        consulta = SQLQuery.objects.filter(pk=3).first()
        consulta = consulta.consulta.format(numero_documento)
        data = ejecutar_consulta_data(conexion, consulta)
        print(data)
        return data
    except:
        return "error Data"

def create_fidelizacion(cliente):
    """
    Crea una tarjeta de fidelización para el cliente si cumple con los requisitos.
    Args:
        cliente: Instancia del cliente a procesar.
    Returns:
        str: Mensaje indicando el resultado de la operación.
    """
    try:
        conexion = conectar_sql_server()
        cursor = conexion.cursor()
                # Verificar si ya tiene tarjeta
        cursor = conexion.cursor()
        cursor.execute("SELECT t.IDTARJETA FROM TARJETAS t WHERE t.CODCLIENTE = ?", (cliente.codcliente,))
        tarjeta = cursor.fetchone()
        nombreCompleto = f'{cliente.primer_nombre or ''} {cliente.segundo_nombre or  ''} {cliente.primer_apellido or  ''} {cliente.segundo_apellido or ''}'.strip()

        if cliente.fidelizacion:
            if tarjeta:
                return "El cliente ya tiene tarjeta."
            else:
                if cliente.tipocliente == 'Cliente' or cliente.tipocliente == 'Colaborador':
                        
                    # Obtener consulta base
                    consulta = SQLQuery.objects.filter(pk=7).first().consulta

                    # Obtener nuevo IDTARJETA
                    cursor.execute("SELECT ISNULL(MAX(IDTARJETA), 0) + 1 FROM TARJETAS")
                    id_tarjeta = cursor.fetchone()[0]
                    fecha_caducidad = datetime(2050, 11, 16)

                    # Insertar usando parámetros
                    valores = (
                        id_tarjeta,
                        cliente.codcliente,
                        1,   # POSICION
                        1,   # IDTIPOTARJETA
                        nombreCompleto,
                        fecha_caducidad,  # Fecha como string, pero SQL Server hará la conversión automática
                        'T',  # VALIDA
                        0,    # SALDO
                        'T',  # ENTREGADA
                        cliente.numero_documento
                    )
                    existe_cliente = getClienteICG(cliente.numero_documento)
                    if existe_cliente:
                        # Ejecutar la consulta de inserción
                        cursor.execute(consulta, valores)
                        conexion.commit()
                        return "Tarjeta creada exitosamente."
                    else:
                        return "El cliente no existe en la base de datos."
                else:
                    return "Es una empresa no fideliza"
    except Exception as e:
        print(f"Error al crear tarjeta: {e}")
        return "Error al crear tarjeta."


def determinar_sucursal(latitud, longitud) -> str:
    """
    Determina la sucursal (zona) a partir de la ubicación del cliente.
    Retorna el nombre de la zona si se encuentra dentro de alguna, o 'CALDAS' si no.

    Args:
        latitud: La latitud del cliente (puede ser None o un número).
        longitud: La longitud del cliente (puede ser None o un número).

    Returns:
        El nombre de la zona o 'CALDAS' como valor por defecto.
    """
    print(f"DEBUG: Iniciando determinar_sucursal con latitud={latitud}, longitud={longitud}") # Depuración

    # 1. Validación de latitud y longitud nulas
    if latitud is None or longitud is None:
        print("DEBUG: Coordenadas nulas, retornando 'CALDAS'.") # Depuración
        return 'CALDAS'

    # 2. Validar tipo y rango de coordenadas
    try:
        lat_float = float(latitud)
        lon_float = float(longitud)
        if not (-90 <= lat_float <= 90) or not (-180 <= lon_float <= 180):
            print(f"DEBUG: Coordenadas fuera de rango: lat={lat_float}, lon={lon_float}. Retornando 'CALDAS'.") # Depuración
            return 'CALDAS'
    except (ValueError, TypeError):
         print(f"DEBUG: Coordenadas no son números válidos: lat='{latitud}', lon='{longitud}'. Retornando 'CALDAS'.") # Depuración
         return 'CALDAS' # Si no se pueden convertir a float, retorna el default

    cliente_ubicacion = (lat_float, lon_float)
    print(f"DEBUG: Ubicación cliente procesada: {cliente_ubicacion}") # Depuración

    try:
        # 3. Obtener zonas activas (optimizando: solo las columnas necesarias)
        zonas = ZonaPermitida.objects.filter(activa=True).values(
            'nombre', 'latitude', 'longitude', 'max_distance'
        )
        print(f"DEBUG: Zonas activas encontradas: {list(zonas)}") # Depuración

        # 4. Iterar sobre las zonas y calcular distancia
        for zona in zonas:
            try:
                # Validar datos de la zona antes de usarlos
                if None in (zona['latitude'], zona['longitude'], zona['max_distance']):
                    print(f"DEBUG: Datos incompletos para zona {zona['nombre']}. Saltando...") # Depuración
                    continue

                centro_zona = (float(zona['latitude']), float(zona['longitude']))
                distancia_max = int(zona['max_distance']) # Asegurar que sea entero para comparar

                # Calcular distancia geodésica
                distancia = geodesic(cliente_ubicacion, centro_zona).meters
                print(f"DEBUG: Calculando para Zona '{zona['nombre']}' ({centro_zona}): Distancia={distancia:.2f}m, Max={distancia_max}m") # Depuración

                # 5. Comprobar si está dentro del radio
                if distancia <= distancia_max:
                    print(f"DEBUG: ¡Encontrado! Cliente dentro de '{zona['nombre']}'.") # Depuración
                    return zona['nombre'] # Encontramos una zona

            except (ValueError, TypeError, KeyError) as e_zona:
                # Error procesando una zona específica (datos inválidos?)
                print(f"DEBUG: Error procesando datos de zona {zona.get('nombre', 'Desconocida')}: {e_zona}. Saltando esta zona.") # Depuración
                continue # Pasar a la siguiente zona

    except Exception as e_db:
        # Capturar error general al acceder a la BD
        print(f"ERROR: No se pudieron obtener las Zonas Permitidas de la BD: {e_db}")
        # Decide si retornar default o relanzar el error dependiendo de tu lógica
        return 'CALDAS' # Retornar default en caso de error de BD

    # 6. Si el bucle termina sin encontrar zona
    print("DEBUG: Cliente fuera de todas las zonas activas. Retornando 'CALDAS'.") # Depuración
    return 'CALDAS'


def actualizar_campos_libres_cliente(cliente):
    try:
        conexion = conectar_sql_server()
        cursor = conexion.cursor()
        if cliente.tipocliente == 'Colaborador':
            validar = 'T'
        else:
            validar = 'F'
        sql_update = """
        UPDATE CLIENTESCAMPOSLIBRES
        SET 
            BARRIO = ?, 
            FECHA_ACTUALIZAR = GETDATE(), -- Usamos la fecha actual
            MASCOTA = ?, 
            SUCURSAL_ALMACEN = ?, 
            TIPO_DE_DOCUMENTO = ?, 
            APELLIDO_1 = ?, 
            APELLIDO_2 = ?, 
            NOMBRE_1 = ?, 
            OTROS_NOMBRES = ?, 
            ORIGENCREACION = ?, 
            SEXO = ?,
            CLIENTE_INTERNO = ?,
            VENTA_INTERNA = ?,
            EDAD = ?,
            HABEAS_DATA = ?,
            OTRA_MASCOTA = ?,
            EMAIL = ?,
            WHATSAPP = ?,
            SMS = ?,
            REDES_SOCIALES = ?,
            LLAMADAS = ?,
            NINGUN_MEDIO = ?,
            IP_USUARIO = ?
        WHERE CODCLIENTE = ?
        """
        ubicacion =  determinar_sucursal(latitud=cliente.latitud, longitud=cliente.longitud)
        # Preparamos los valores
        valores = (
            cliente.barrio or '',                       # BARRIO
            cliente.mascota or 'NO TIENE',                # MASCOTA
            cliente.punto_compra or ubicacion or 'CALDAS',                                # SUCURSAL_ALMACEN (valor fijo, o podrías adaptarlo)
            cliente.tipocliente or 'CC',                # TIPO_DE_DOCUMENTO ('CC' por defecto si no hay tipo)
            cliente.primer_apellido or '',              # APELLIDO_1
            cliente.segundo_apellido or '',             # APELLIDO_2
            cliente.primer_nombre or '',                # NOMBRE_1
            cliente.segundo_nombre or '',               # OTROS_NOMBRES
            ubicacion or 'CALDAS',                                 # ORIGENCREACION (puedes cambiarlo si quieres)
            cliente.genero,                             # SEXO (podrías mapear de alguna forma si tienes ese dato)
            validar or 'F',           # CLIENTE_INTERNO
            validar or 'F',             # VENTA_INTERNA
            calcular_edad(cliente.fecha_nacimiento) or 0, # EDA
            bool_a_tf(cliente.acepto_politica) or 'F',                  # HABEAS_DATA
            cliente.otra_mascota or 'NO TIENE',                # OTRA_MACOSTA
            bool_a_tf(cliente.preferencias_email) or 'F',                       # EMAIL
            bool_a_tf(cliente.preferencias_whatsapp) or 'F',                      # WHATSAPP
            bool_a_tf(cliente.preferencias_sms) or 'F',                      # SMS
            bool_a_tf(cliente.preferencias_redes_sociales) or 'F',               # REDES_SOCIALES
            bool_a_tf(cliente.preferencias_llamada) or 'F',                     # LLAMADAS
            bool_a_tf(cliente.preferencias_ninguna) or 'F',                 # NINGUN_MEDIO
            cliente.ip_usuario or 'F',                   # IP_USUARIO
            cliente.codcliente                         # CODCLIENTE
        )

        cursor.execute(sql_update, valores)
        conexion.commit()
        print(f"Cliente {cliente.codcliente} actualizado correctamente en CLIENTESCAMPOSLIBRES.")

    except Exception as e:
        print("Error al actualizar cliente en CLIENTESCAMPOSLIBRES:", e)


def ConsultarClienteICG(numero_documento):
    try:
        data = getClienteICG(numero_documento)
        print(data)
        cliente = RegistroCliente.objects.filter(numero_documento = numero_documento)
        if cliente:
            print("Cliente Existe")
            return
        else:
            cliente = RegistroCliente(
                codcliente = data[0][0],
                numero_documento = data[0][1],
                primer_nombre = data[0][2],
                segundo_nombre = data[0][3],
                primer_apellido = data[0][4],
                segundo_apellido = data[0][5],
                fecha_nacimiento = data[0][6],
            )
            cliente.save()
    except:
        return "error"
    return data


def crearClienteICG(intanse_cliente):
    nombreCompleto = f'{intanse_cliente.primer_nombre or ''} {intanse_cliente.segundo_nombre or  ''} {intanse_cliente.primer_apellido or  ''} {intanse_cliente.segundo_apellido or ''}'.strip()
    if intanse_cliente.tipocliente == 'Clientes':
        tipocliente = 14
    elif intanse_cliente.tipocliente == 'Colaborador':
        tipocliente = 20
    elif intanse_cliente.tipocliente == 'Empresa':
        tipocliente = 5
    else :
        tipocliente = 14
    try:
        conexion = conectar_sql_server()
        cursor = conexion.cursor()
        consulta = SQLQuery.objects.filter(pk=6).first().consulta
        valores = (
            generar_nuevo_codcliente(),                     # CODCLIENTE (Usamos el mismo que el número de documento)
            '13050501',                                     # CODCONTABLE (Valor predeterminado del SQL)
            nombreCompleto,                                 # NOMBRECLIENTE
            nombreCompleto,                                 # NOMBRECOMERCIAL (Usamos el mismo que NOMBRECLIENTE)
            intanse_cliente.numero_documento,     # CIF
            intanse_cliente.numero_documento,     # ALIAS (Usamos el mismo que CIF)
            f'{intanse_cliente.tipo_via} {intanse_cliente.direccion}' or '',      # DIRECCION1 (Usar cadena vacía si es NULL localmente)
            '680001',                                       # CODPOSTAL (Valor predeterminado del SQL) - No está en tu modelo Django
            intanse_cliente.ciudad or '',         # POBLACION
            'SANTANDER',                                    # PROVINCIA (Valor predeterminado del SQL) - No está en tu modelo Django
            'Colombia',                                     # PAIS (Valor predeterminado del SQL) - No está en tu modelo Django
            intanse_cliente.telefono or '',       # TELEFONO1
            intanse_cliente.celular or '',                                           # TELEFONO2 (NULL en tu SQL)
            intanse_cliente.correo or '',         # E_MAIL
            0,                                              # CANTPORTESPAG (Valor predeterminado del SQL)
            'D',                                            # TIPOPORTES (Valor predeterminado del SQL)
            0,                                              # NUMDIASENTREGA (Valor predeterminado del SQL)
            1,                                              # RIESGOCONCEDIDO (Valor predeterminado del SQL)
            tipocliente,                                             # TIPO (Valor predeterminado del SQL)
            'F',                                            # RECARGO (Valor predeterminado del SQL) - Ojo: 'F' puede ser un booleano en ICG
            0,                                              # DIAPAGO1 (Valor predeterminado del SQL)
            0,                                              # DIAPAGO2 (Valor predeterminado del SQL)
            'F',                                            # FACTURARSINIMPUESTOS (Valor predeterminado del SQL)
            0,                                              # DTOCOMERCIAL (Valor predeterminado del SQL)
            'G',                                            # REGIMFACT (Valor predeterminado del SQL)
            1,                                              # CODMONEDA (Valor predeterminado del SQL)
            intanse_cliente.fecha_nacimiento,     # FECHANACIMIENTO (pyodbc maneja objetos date de Python)
            intanse_cliente.numero_documento,     # NIF20 (Usamos el mismo que CIF)
            'F',                                            # DESCATALOGADO (Valor predeterminado del SQL)
            'L',                                            # LOCAL_REMOTA (Valor predeterminado del SQL)
            2,                                           # CODVISIBLE (NULL en tu SQL)
            'CO',                                           # CODPAIS (Valor predeterminado del SQL) - No está en tu modelo Django
            None,                                           # CARGOSFIJOSA (NULL en tu SQL)
            intanse_cliente.celular or '',        # MOBIL
            0,                                              # NOCALCULARCARGO1ARTIC (Valor predeterminado del SQL)
            0,                                              # NOCALCULARCARGO2ARTIC (Valor predeterminado del SQL)
            0,                                              # ESCLIENTEDELGRUPO (Valor predeterminado del SQL)
            0,                                              # RET_TIPORETENCIONIVA (Valor predeterminado del SQL)
            0,                                              # CAMPOSLIBRESTOTALIZAR (Valor predeterminado del SQL)
            0,                                              # BLOQUEADO (Valor predeterminado del SQL)
            0,                                              # TIPODOCIDENT (Valor predeterminado del SQL)
            'L',                                            # PERSONAJURIDICA (Valor predeterminado del SQL) - Asumimos 'L' literal del SQL
            1 if intanse_cliente.preferencias_email else 0, # RECIBIRINFORMACION (Mapeamos preferencia_email a 1/0)
            0,                                              # MAXIMOVENTA_APLICAR (Valor predeterminado del SQL)
            0,                                              # ENVIARMAILCHECKIN (Valor predeterminado del SQL)
            0,                                              # ENVIARMAILCHECKOUT (Valor predeterminado del SQL)
            0,                                              # FORZARNOIMPRIMIR (Valor predeterminado del SQL)
            0,                                              # TIPO_EXCEP_SII (Valor predeterminado del SQL)
            0,                                              # NOCALCULARCARGO3ARTIC (Valor predeterminado del SQL)
            0,                                              # NOCALCULARCARGO4ARTIC (Valor predeterminado del SQL)
            0,                                              # NOCALCULARCARGO5ARTIC (Valor predeterminado del SQL)
            0                                               # NOCALCULARCARGO6ARTIC (Valor predeterminado del SQL)
        )
        try:
            cursor.execute(consulta, valores)
            conexion.commit()
        except Exception as e:
            conexion.rollback()
            print(f"Error al ejecutar la consulta: {e}")
        cliente = getClienteICG(intanse_cliente.numero_documento)
        if cliente:
            intanse_cliente.codcliente = cliente[0][0]
            intanse_cliente.creadoICG = True
            intanse_cliente.save()
            actualizar_campos_libres_cliente(intanse_cliente)
            create_fidelizacion(intanse_cliente)
            intanse_cliente.Actualizado = False
            intanse_cliente.save()
            if intanse_cliente.correo_notificacion == True:
                print("proceso de enviar correo")
                enviar_correo(intanse_cliente)
        else:
            print("error codcliente")

    except:
        return 'error'


def actualizarClienteICG(intanse_cliente):
    conexion = conectar_sql_server()
    cursor = conexion.cursor()

    nombreCompleto = f'{intanse_cliente.primer_nombre or ''} {intanse_cliente.segundo_nombre or  ''} {intanse_cliente.primer_apellido or  ''} {intanse_cliente.segundo_apellido or ''}'.strip()

    campos = []
    valores = []

    print("Ingreso:", nombreCompleto)

    if intanse_cliente.primer_nombre or intanse_cliente.primer_apellido:
        campos.append('NOMBRECLIENTE = ?')
        campos.append('NOMBRECOMERCIAL = ?')
        valores.append(nombreCompleto)
        valores.append(nombreCompleto)

    if intanse_cliente.direccion:
        direccion_completa = f'{intanse_cliente.tipo_via or ""} {intanse_cliente.direccion}'.strip()
        campos.append('DIRECCION1 = ?')
        valores.append(direccion_completa)

    if intanse_cliente.telefono:
        campos.append('TELEFONO1 = ?')
        valores.append(intanse_cliente.telefono)

    if intanse_cliente.celular:
        campos.append('TELEFONO2 = ?')
        valores.append(intanse_cliente.celular)

    if intanse_cliente.correo:
        campos.append('E_MAIL = ?')
        valores.append(intanse_cliente.correo)

    if intanse_cliente.fecha_nacimiento:
        campos.append('FECHANACIMIENTO = ?')
        valores.append(intanse_cliente.fecha_nacimiento)
    
    if intanse_cliente.tipocliente:
        if intanse_cliente.tipocliente == 'Clientes':
            tipocliente = 14
        elif intanse_cliente.tipocliente == 'Colaborador':
            tipocliente = 20
        elif intanse_cliente.tipocliente == 'Empresa':
            tipocliente = 5
        else :
            tipocliente = 14
        campos.append('TIPO = ?')
        valores.append(tipocliente)

    if not campos:
        print("No hay cambios para actualizar.")
        return 'No hay cambios'

    set_clause = ", ".join(campos)
    sql = f"UPDATE CLIENTES SET {set_clause} WHERE CODCLIENTE = ?"
    valores.append(intanse_cliente.codcliente)

    # ---- Mostrar el SQL con valores reales ----
    sql_mostrar = sql
    for valor in valores:
        if isinstance(valor, str):
            valor_reemplazo = f"'{valor}'"
        elif valor is None:
            valor_reemplazo = 'NULL'
        else:
            valor_reemplazo = str(valor)
        sql_mostrar = sql_mostrar.replace('?', valor_reemplazo, 1)

    print("SQL con valores reales:", sql_mostrar)
    # --------------------------------------------

    try:
        cursor.execute(sql, valores)
        conexion.commit()
        intanse_cliente.Actualizado = True
        intanse_cliente.save()
        actualizar_campos_libres_cliente(intanse_cliente)
        create_fidelizacion(intanse_cliente)
        if intanse_cliente.correo_notificacion == True:
            enviar_correo(intanse_cliente)
        return 'Cliente actualizado exitosamente'
    except Exception as e:
        print(e)
        return 'error'
    