#!/usr/bin/env python
"""
Script para migrar datos de marca (ForeignKey eliminado) a marcas (ManyToMany).
Recupera las marcas desde las líneas de cada lote.
"""
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'appMercaSur.settings')
django.setup()

from Compras.models import SugeridoLote, SugeridoLinea

def migrar_marcas():
    lotes_actualizados = 0
    lotes_sin_marcas = 0
    
    print("Iniciando migración de marcas...")
    
    for lote in SugeridoLote.objects.all():
        # Obtener marcas únicas de las líneas de este lote
        marcas_ids = SugeridoLinea.objects.filter(
            lote=lote
        ).values_list('marca_id', flat=True).distinct()
        
        # Filtrar None
        marcas_ids = [m for m in marcas_ids if m is not None]
        
        if marcas_ids:
            lote.marcas.set(marcas_ids)
            lotes_actualizados += 1
            print(f"  Lote {lote.id} ({lote.nombre}): {len(marcas_ids)} marca(s) asignada(s)")
        else:
            lotes_sin_marcas += 1
            print(f"  Lote {lote.id} ({lote.nombre}): Sin marcas")
    
    print(f"\n✅ Migración completada:")
    print(f"   - {lotes_actualizados} lotes actualizados con sus marcas")
    print(f"   - {lotes_sin_marcas} lotes sin marcas")

if __name__ == '__main__':
    migrar_marcas()
