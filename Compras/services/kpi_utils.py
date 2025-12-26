"""
Utilidades para cálculo y visualización de KPIs de inventario
"""
from decimal import Decimal
from typing import Dict, List, Optional
from django.db.models import Sum, Avg, Count, Q
from ..models import SugeridoLinea, SugeridoLote


def obtener_kpis_por_lote(lote_id: int) -> Dict:
    """
    Obtiene KPIs agregados de un lote específico de sugerido.
    
    Args:
        lote_id: ID del SugeridoLote
    
    Returns:
        Diccionario con KPIs calculados:
        - valor_total_inventario: Suma del valor de inventario de todas las líneas
        - dias_inventario_promedio: Promedio de días de inventario
        - dias_inventario_mediana: Mediana aproximada de días de inventario
        - total_unidades_stock: Total de unidades en stock
        - total_articulos: Cantidad de artículos únicos
        - total_lineas: Cantidad total de líneas
        - articulos_sin_venta: Cantidad de artículos sin ventas en 90 días
        - porcentaje_sin_venta: % de artículos sin ventas
    """
    from django.db.models import Q, Case, When, IntegerField
    
    lineas = SugeridoLinea.objects.filter(lote_id=lote_id)
    
    # Agregaciones básicas
    agregados = lineas.aggregate(
        valor_total=Sum('valor_inventario'),
        dias_promedio=Avg('dias_inventario'),
        unidades_total=Sum('stock_actual'),
        total_lineas=Count('id'),
        articulos_sin_venta=Count('id', filter=Q(unidades_vendidas_90d=0)),
    )
    
    # Contar artículos únicos
    total_articulos = lineas.values('codigo_articulo', 'cod_almacen').distinct().count()
    
    # Calcular mediana aproximada (usando percentil 50)
    # Nota: Para PostgreSQL puedes usar percentile_cont, para otros DBs esto es una aproximación
    lineas_ordenadas = list(
        lineas.filter(dias_inventario__isnull=False)
        .order_by('dias_inventario')
        .values_list('dias_inventario', flat=True)
    )
    
    dias_mediana = None
    if lineas_ordenadas:
        n = len(lineas_ordenadas)
        if n % 2 == 0:
            dias_mediana = float((lineas_ordenadas[n//2 - 1] + lineas_ordenadas[n//2]) / 2)
        else:
            dias_mediana = float(lineas_ordenadas[n//2])
    
    # Calcular porcentaje sin venta
    porcentaje_sin_venta = 0.0
    if agregados['total_lineas'] > 0:
        porcentaje_sin_venta = (agregados['articulos_sin_venta'] / agregados['total_lineas']) * 100
    
    return {
        'valor_total_inventario': float(agregados['valor_total'] or 0),
        'dias_inventario_promedio': float(agregados['dias_promedio'] or 0),
        'dias_inventario_mediana': dias_mediana,
        'total_unidades_stock': float(agregados['unidades_total'] or 0),
        'total_articulos': total_articulos,
        'total_lineas': agregados['total_lineas'],
        'articulos_sin_venta': agregados['articulos_sin_venta'],
        'porcentaje_sin_venta': round(porcentaje_sin_venta, 2),
    }


def obtener_kpis_por_almacen(lote_id: int) -> List[Dict]:
    """
    Obtiene KPIs desglosados por almacén para un lote específico.
    
    Args:
        lote_id: ID del SugeridoLote
    
    Returns:
        Lista de diccionarios con KPIs por almacén
    """
    lineas = SugeridoLinea.objects.filter(lote_id=lote_id)
    
    almacenes = lineas.values('cod_almacen', 'nombre_almacen').distinct()
    
    resultado = []
    for alm in almacenes:
        cod_alm = alm['cod_almacen']
        lineas_alm = lineas.filter(cod_almacen=cod_alm)
        
        agregados = lineas_alm.aggregate(
            valor_total=Sum('valor_inventario'),
            dias_promedio=Avg('dias_inventario'),
            unidades_total=Sum('stock_actual'),
            total_lineas=Count('id'),
            articulos_sin_venta=Count('id', filter=Q(unidades_vendidas_90d=0)),
        )
        
        resultado.append({
            'cod_almacen': cod_alm,
            'nombre_almacen': alm['nombre_almacen'],
            'valor_total_inventario': float(agregados['valor_total'] or 0),
            'dias_inventario_promedio': float(agregados['dias_promedio'] or 0),
            'total_unidades_stock': float(agregados['unidades_total'] or 0),
            'total_lineas': agregados['total_lineas'],
            'articulos_sin_venta': agregados['articulos_sin_venta'],
        })
    
    return resultado


def obtener_kpis_por_clasificacion(lote_id: int) -> List[Dict]:
    """
    Obtiene KPIs desglosados por clasificación ABC para un lote específico.
    
    Args:
        lote_id: ID del SugeridoLote
    
    Returns:
        Lista de diccionarios con KPIs por clasificación
    """
    lineas = SugeridoLinea.objects.filter(lote_id=lote_id)
    
    clasificaciones = lineas.values('clasificacion').distinct()
    
    resultado = []
    for clf in clasificaciones:
        clasificacion = clf['clasificacion'] or 'SIN CLASIFICAR'
        lineas_clf = lineas.filter(clasificacion=clf['clasificacion'])
        
        agregados = lineas_clf.aggregate(
            valor_total=Sum('valor_inventario'),
            dias_promedio=Avg('dias_inventario'),
            unidades_total=Sum('stock_actual'),
            total_lineas=Count('id'),
            costo_total=Sum('costo_linea'),
        )
        
        resultado.append({
            'clasificacion': clasificacion,
            'valor_total_inventario': float(agregados['valor_total'] or 0),
            'dias_inventario_promedio': float(agregados['dias_promedio'] or 0),
            'total_unidades_stock': float(agregados['unidades_total'] or 0),
            'total_lineas': agregados['total_lineas'],
            'costo_total_sugerido': float(agregados['costo_total'] or 0),
        })
    
    # Ordenar por valor total descendente
    resultado.sort(key=lambda x: x['valor_total_inventario'], reverse=True)
    
    return resultado


def obtener_articulos_criticos(lote_id: int, dias_minimo: int = 7) -> List[Dict]:
    """
    Obtiene artículos con días de inventario por debajo del mínimo especificado.
    
    Args:
        lote_id: ID del SugeridoLote
        dias_minimo: Umbral mínimo de días de inventario (default: 7)
    
    Returns:
        Lista de artículos críticos con sus datos
    """
    lineas = SugeridoLinea.objects.filter(
        lote_id=lote_id,
        dias_inventario__lt=dias_minimo,
        dias_inventario__isnull=False
    ).order_by('dias_inventario')
    
    resultado = []
    for linea in lineas[:100]:  # Limitar a 100 artículos
        resultado.append({
            'codigo_articulo': linea.codigo_articulo,
            'descripcion': linea.descripcion,
            'almacen': linea.nombre_almacen,
            'clasificacion': linea.clasificacion,
            'stock_actual': float(linea.stock_actual),
            'dias_inventario': float(linea.dias_inventario) if linea.dias_inventario else None,
            'venta_diaria_promedio': float(linea.venta_diaria_promedio),
            'sugerido_calculado': float(linea.sugerido_calculado),
            'costo_linea': float(linea.costo_linea),
        })
    
    return resultado


def obtener_articulos_exceso(lote_id: int, dias_maximo: int = 60) -> List[Dict]:
    """
    Obtiene artículos con exceso de inventario (días > máximo especificado).
    
    Args:
        lote_id: ID del SugeridoLote
        dias_maximo: Umbral máximo de días de inventario (default: 60)
    
    Returns:
        Lista de artículos con exceso de inventario
    """
    lineas = SugeridoLinea.objects.filter(
        lote_id=lote_id,
        dias_inventario__gt=dias_maximo
    ).order_by('-dias_inventario')
    
    resultado = []
    for linea in lineas[:100]:  # Limitar a 100 artículos
        resultado.append({
            'codigo_articulo': linea.codigo_articulo,
            'descripcion': linea.descripcion,
            'almacen': linea.nombre_almacen,
            'clasificacion': linea.clasificacion,
            'stock_actual': float(linea.stock_actual),
            'dias_inventario': float(linea.dias_inventario),
            'venta_diaria_promedio': float(linea.venta_diaria_promedio),
            'valor_inventario': float(linea.valor_inventario),
        })
    
    return resultado
