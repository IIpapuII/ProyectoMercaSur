from decimal import Decimal
import math

def calcular_sugerido_inteligente(stock_actual: Decimal, stock_maximo: Decimal, embalaje: int, clasificacion: str = None) -> Decimal:
    """
    Calcula el sugerido de compra de manera inteligente según el embalaje y el stock máximo.
    
    Lógica:
    0. Si clasificación es I: retornar 0 (no se debe pedir)
    1. Calcular unidades faltantes para llegar al máximo
    2. Si las unidades faltantes < 50% embalaje: retornar 0 (no vale la pena pedir)
    3. Si las unidades faltantes >= 50% embalaje: redondear al embalaje completo
    4. Si embalaje <= stock_maximo: comprar múltiplo de embalaje necesario
    5. Si embalaje > stock_maximo: trabajar con fracciones de embalaje
    
    Args:
        stock_actual: Stock actual en almacén
        stock_maximo: Stock máximo configurado
        embalaje: Unidades por caja/embalaje
        clasificacion: Clasificación del artículo (A, B, C, I, etc.)
    
    Returns:
        Cantidad sugerida a pedir (0 si clasificación I, o si no alcanza para 50% del embalaje)
    """
    # VALIDACIÓN: Si clasificación es I, retornar 0
    if clasificacion:
        cla_upper = str(clasificacion).strip().upper()
        if cla_upper in {'I',}:
            return Decimal("0")
    
    # Convertir a Decimal para precisión
    stock_actual = Decimal(str(stock_actual)) if stock_actual else Decimal("0")
    stock_maximo = Decimal(str(stock_maximo)) if stock_maximo else Decimal("0")
    embalaje = int(embalaje) if embalaje and embalaje > 0 else 1
    
    # Calcular unidades faltantes para llegar al máximo
    unidades_faltantes = stock_maximo - stock_actual
    
    # Si no faltan unidades o ya estamos sobre el máximo, no pedir nada
    if unidades_faltantes <= 0:
        return Decimal("0")
    
    # NUEVA REGLA CLAVE: Si las unidades faltantes son menores que el 50% del embalaje, retornar 0
    # Esto evita pedidos muy pequeños que no justifican abrir una caja
    umbral_minimo = Decimal(embalaje) * Decimal("0.5")
    if unidades_faltantes < umbral_minimo:
        return Decimal("0")
    
    # Caso 1: Embalaje menor o igual al máximo
    # Solo pedimos lo necesario para llegar al máximo (múltiplo del embalaje)
    if embalaje <= stock_maximo:
        # Calcular cuántas cajas completas caben y el resto
        cajas_completas = int(unidades_faltantes // embalaje)
        resto = float(unidades_faltantes % embalaje)
        
        # Si el resto es >= 50% del embalaje, agregar una caja más
        if resto >= embalaje * 0.5:
            cajas_necesarias = cajas_completas + 1
        else:
            cajas_necesarias = cajas_completas
        
        sugerido = Decimal(cajas_necesarias * embalaje)
        
        # Si no hay cajas completas pero el total es >= 50%, dar 1 caja
        if sugerido == 0 and unidades_faltantes >= umbral_minimo:
            sugerido = Decimal(embalaje)
        
        return sugerido
    
    # Caso 2: Embalaje mayor al máximo
    # Dividir el embalaje por 2 y trabajar con "medio cajas"
    else:
        medio_embalaje = embalaje // 2
        
        # Si medio embalaje aún es menor que unidades faltantes, usar medio embalaje
        if medio_embalaje > 0 and unidades_faltantes >= medio_embalaje:
            # Si medio embalaje sigue siendo muy grande, usar cuarto de embalaje
            if medio_embalaje > stock_maximo:
                cuarto_embalaje = embalaje // 4
                if cuarto_embalaje > 0 and unidades_faltantes >= cuarto_embalaje:
                    # Aplicar la misma lógica de 50%
                    umbral_cuarto = Decimal(cuarto_embalaje) * Decimal("0.50")
                    resto = float(unidades_faltantes) % cuarto_embalaje
                    
                    if resto >= float(umbral_cuarto):
                        medio_cajas_necesarias = math.ceil(float(unidades_faltantes) / cuarto_embalaje)
                    else:
                        medio_cajas_necesarias = math.floor(float(unidades_faltantes) / cuarto_embalaje)
                    
                    return Decimal(medio_cajas_necesarias * cuarto_embalaje)
            
            # Aplicar la misma lógica de 50% para medio embalaje
            umbral_medio = Decimal(medio_embalaje) * Decimal("0.50")
            resto = float(unidades_faltantes) % medio_embalaje
            
            if resto >= float(umbral_medio):
                medio_cajas_necesarias = math.ceil(float(unidades_faltantes) / medio_embalaje)
            else:
                medio_cajas_necesarias = math.floor(float(unidades_faltantes) / medio_embalaje)
            
            sugerido = Decimal(medio_cajas_necesarias * medio_embalaje)
            return sugerido
        
        # Si ni siquiera llega a medio embalaje, retornar 0
        return Decimal("0")


def ajustar_sugerido_con_embalaje(sugerido_base: Decimal, embalaje: int, clasificacion: str = None) -> Decimal:
    """
    Ajusta un sugerido base para que sea múltiplo del embalaje.
    Si clasificación es I, retorna 0.
    Si el sugerido base es menor que 50% del embalaje, retorna 0.
    Si el resto del sugerido es >= 50% del embalaje, redondea hacia arriba.
    Si el resto del sugerido es < 50% del embalaje, redondea hacia abajo.
    
    Args:
        sugerido_base: Cantidad sugerida inicial
        embalaje: Unidades por caja/embalaje
        clasificacion: Clasificación del artículo (A, B, C, I, etc.)
    
    Returns:
        Sugerido ajustado al múltiplo de embalaje (0 si clasificación I o no alcanza para 50% de una caja)
    """
    # VALIDACIÓN: Si clasificación es I, retornar 0
    if clasificacion:
        cla_upper = str(clasificacion).strip().upper()
        if cla_upper in {'I'}:
            return Decimal("0")
    
    if not sugerido_base or sugerido_base <= 0:
        return Decimal("0")
    
    embalaje = int(embalaje) if embalaje and embalaje > 0 else 1
    
    # NUEVA REGLA: Si el sugerido es menor que 50% del embalaje, retornar 0
    umbral_minimo = Decimal(embalaje) * Decimal("0.5")
    if sugerido_base < umbral_minimo:
        return Decimal("0")
    
    # Calcular cuántas cajas completas caben y el resto
    cajas_completas = int(sugerido_base // embalaje)
    resto = float(sugerido_base % embalaje)
    
    # Si el resto es >= 50% del embalaje, redondear hacia arriba
    if resto >= embalaje * 0.5:
        cajas = cajas_completas + 1
    else:
        cajas = cajas_completas
    
    sugerido = Decimal(cajas * embalaje)
    
    # Si no hay cajas completas pero el total es >= 50%, dar al menos 1 caja
    if sugerido == 0 and sugerido_base >= umbral_minimo:
        sugerido = Decimal(embalaje)
    
    return sugerido
