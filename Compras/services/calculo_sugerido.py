from decimal import Decimal
import math

def calcular_sugerido_inteligente(stock_actual: Decimal, stock_maximo: Decimal, embalaje: int, clasificacion: str = None) -> Decimal:
    """
    Calcula el sugerido de compra de manera inteligente según el embalaje y el stock máximo.
    
    Lógica:
    0. Si clasificación es I o C: retornar 0 (no se debe pedir)
    1. Calcular unidades faltantes para llegar al máximo
    2. Si las unidades faltantes < embalaje: retornar 0 (no vale la pena pedir)
    3. Si embalaje <= stock_maximo: comprar múltiplo de embalaje necesario
    4. Si embalaje > stock_maximo: trabajar con fracciones de embalaje
    
    Args:
        stock_actual: Stock actual en almacén
        stock_maximo: Stock máximo configurado
        embalaje: Unidades por caja/embalaje
        clasificacion: Clasificación del artículo (A, B, C, I, etc.)
    
    Returns:
        Cantidad sugerida a pedir (0 si clasificación I/C, o si no alcanza para un embalaje completo)
    """
    # NUEVA VALIDACIÓN: Si clasificación es I o C, retornar 0
    if clasificacion:
        cla_upper = str(clasificacion).strip().upper()
        if cla_upper in {'I', 'C'}:
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
    
    # REGLA CLAVE: Si las unidades faltantes son menores que el embalaje, retornar 0
    # No tiene sentido pedir una caja completa si solo necesitamos menos de una caja
    if unidades_faltantes < embalaje:
        return Decimal("0")
    
    # Caso 1: Embalaje menor o igual al máximo
    # Solo pedimos lo necesario para llegar al máximo (múltiplo del embalaje)
    if embalaje <= stock_maximo:
        # Redondear hacia arriba al múltiplo de embalaje más cercano
        cajas_necesarias = math.ceil(float(unidades_faltantes) / embalaje)
        sugerido = Decimal(cajas_necesarias * embalaje)
        
        # Si el sugerido nos pasa mucho del máximo, ajustar
        if sugerido > unidades_faltantes and cajas_necesarias > 1:
            # Intentar con una caja menos si es razonable
            sugerido_alternativo = Decimal((cajas_necesarias - 1) * embalaje)
            # Solo usar alternativa si cubre al menos 80% de lo necesario
            if sugerido_alternativo >= unidades_faltantes * Decimal("0.8"):
                return sugerido_alternativo
        
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
                    medio_cajas_necesarias = math.ceil(float(unidades_faltantes) / cuarto_embalaje)
                    return Decimal(medio_cajas_necesarias * cuarto_embalaje)
            
            # Calcular cuántas "medio cajas" necesitamos
            medio_cajas_necesarias = math.ceil(float(unidades_faltantes) / medio_embalaje)
            sugerido = Decimal(medio_cajas_necesarias * medio_embalaje)
            return sugerido
        
        # Si ni siquiera llega a medio embalaje, retornar 0
        return Decimal("0")


def ajustar_sugerido_con_embalaje(sugerido_base: Decimal, embalaje: int, clasificacion: str = None) -> Decimal:
    """
    Ajusta un sugerido base para que sea múltiplo del embalaje.
    Si clasificación es I o C, retorna 0.
    Si el sugerido base es menor que el embalaje, retorna 0.
    
    Args:
        sugerido_base: Cantidad sugerida inicial
        embalaje: Unidades por caja/embalaje
        clasificacion: Clasificación del artículo (A, B, C, I, etc.)
    
    Returns:
        Sugerido ajustado al múltiplo de embalaje (0 si clasificación I/C o no alcanza para una caja)
    """
    # NUEVA VALIDACIÓN: Si clasificación es I o C, retornar 0
    if clasificacion:
        cla_upper = str(clasificacion).strip().upper()
        if cla_upper in {'I', 'C'}:
            return Decimal("0")
    
    if not sugerido_base or sugerido_base <= 0:
        return Decimal("0")
    
    embalaje = int(embalaje) if embalaje and embalaje > 0 else 1
    
    # Si el sugerido es menor que el embalaje, retornar 0
    if sugerido_base < embalaje:
        return Decimal("0")
    
    # Redondear hacia arriba al múltiplo de embalaje
    cajas = math.ceil(float(sugerido_base) / embalaje)
    return Decimal(cajas * embalaje)
