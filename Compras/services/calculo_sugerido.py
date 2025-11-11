from decimal import Decimal
import math

def calcular_sugerido_inteligente(stock_actual: Decimal, stock_maximo: Decimal, embalaje: int) -> Decimal:
    """
    Calcula el sugerido de compra de manera inteligente según el embalaje y el stock máximo.
    
    Lógica:
    1. Si embalaje <= stock_maximo: comprar solo lo necesario para llegar al máximo
    2. Si embalaje > stock_maximo: 
       - Dividir embalaje por 2
       - Calcular cuántas "medio-cajas" se necesitan
       - Redondear hacia arriba y multiplicar por medio embalaje
    
    Args:
        stock_actual: Stock actual en almacén
        stock_maximo: Stock máximo configurado
        embalaje: Unidades por caja/embalaje
    
    Returns:
        Cantidad sugerida a pedir
    """
    # Convertir a Decimal para precisión
    stock_actual = Decimal(str(stock_actual)) if stock_actual else Decimal("0")
    stock_maximo = Decimal(str(stock_maximo)) if stock_maximo else Decimal("0")
    embalaje = int(embalaje) if embalaje and embalaje > 0 else 1
    
    # Calcular unidades faltantes para llegar al máximo
    unidades_faltantes = stock_maximo - stock_actual
    
    # Si no faltan unidades o ya estamos sobre el máximo, no pedir nada
    if unidades_faltantes <= 0:
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
            if sugerido_alternativo >= unidades_faltantes * Decimal("0.8"):
                return sugerido_alternativo
        
        return sugerido
    
    # Caso 2: Embalaje mayor al máximo
    # Dividir el embalaje por 2 y trabajar con "medio cajas"
    else:
        medio_embalaje = embalaje // 2
        
        # Si medio embalaje sigue siendo muy grande, usar cuarto de embalaje
        if medio_embalaje > stock_maximo:
            cuarto_embalaje = embalaje // 4
            if cuarto_embalaje > 0:
                medio_cajas_necesarias = math.ceil(float(unidades_faltantes) / cuarto_embalaje)
                return Decimal(medio_cajas_necesarias * cuarto_embalaje)
        
        # Calcular cuántas "medio cajas" necesitamos
        medio_cajas_necesarias = math.ceil(float(unidades_faltantes) / medio_embalaje)
        sugerido = Decimal(medio_cajas_necesarias * medio_embalaje)
        
        return sugerido


def ajustar_sugerido_con_embalaje(sugerido_base: Decimal, embalaje: int) -> Decimal:
    """
    Ajusta un sugerido base para que sea múltiplo del embalaje.
    
    Args:
        sugerido_base: Cantidad sugerida inicial
        embalaje: Unidades por caja/embalaje
    
    Returns:
        Sugerido ajustado al múltiplo de embalaje más cercano (hacia arriba)
    """
    if not sugerido_base or sugerido_base <= 0:
        return Decimal("0")
    
    embalaje = int(embalaje) if embalaje and embalaje > 0 else 1
    
    # Redondear hacia arriba al múltiplo de embalaje
    cajas = math.ceil(float(sugerido_base) / embalaje)
    return Decimal(cajas * embalaje)
