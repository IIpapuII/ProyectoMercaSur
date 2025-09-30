#!/usr/bin/env python
"""
Script para crear datos de prueba para la funcionalidad de marcas y proveedores
"""

import os
import sys
import django

# Configurar Django
sys.path.append('/Users/iipapuii/Pictures/PROYECTOS/ProyectoMercaSur')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'appMercaSur.settings')
django.setup()

from django.contrib.auth import get_user_model
from Compras.models import Proveedor, Marca, AsignacionMarcaVendedor, VendedorPerfil, ProveedorUsuario

User = get_user_model()

def create_test_data():
    print("Creando datos de prueba...")
    
    # Crear proveedores
    proveedor1, created = Proveedor.objects.get_or_create(
        nombre="Proveedor Prueba 1",
        defaults={'nit': '123456789', 'email_contacto': 'proveedor1@test.com'}
    )
    
    proveedor2, created = Proveedor.objects.get_or_create(
        nombre="Proveedor Prueba 2", 
        defaults={'nit': '987654321', 'email_contacto': 'proveedor2@test.com'}
    )
    
    print(f"Proveedores creados: {proveedor1}, {proveedor2}")
    
    # Crear marcas
    marca1, created = Marca.objects.get_or_create(nombre="Marca A")
    marca2, created = Marca.objects.get_or_create(nombre="Marca B")
    marca3, created = Marca.objects.get_or_create(nombre="Marca C")
    
    print(f"Marcas creadas: {marca1}, {marca2}, {marca3}")
    
    # Crear usuario vendedor si no existe
    try:
        admin_user = User.objects.get(username='admin')
    except User.DoesNotExist:
        admin_user = User.objects.create_superuser('admin', 'admin@test.com', 'admin123')
        print("Usuario admin creado")
    
    # Crear perfil vendedor
    vendedor_perfil, created = VendedorPerfil.objects.get_or_create(
        user=admin_user,
        defaults={'alias': 'Vendedor Test'}
    )
    
    print(f"Vendedor perfil: {vendedor_perfil}")
    
    # Crear asignaciones
    asignacion1, created = AsignacionMarcaVendedor.objects.get_or_create(
        proveedor=proveedor1,
        marca=marca1,
        vendedor=vendedor_perfil
    )
    
    asignacion2, created = AsignacionMarcaVendedor.objects.get_or_create(
        proveedor=proveedor1,
        marca=marca2,
        vendedor=vendedor_perfil
    )
    
    asignacion3, created = AsignacionMarcaVendedor.objects.get_or_create(
        proveedor=proveedor2,
        marca=marca3,
        vendedor=vendedor_perfil
    )
    
    print(f"Asignaciones creadas: {asignacion1}, {asignacion2}, {asignacion3}")
    
    # Mostrar resumen
    print("\n=== RESUMEN ===")
    print(f"Proveedores: {Proveedor.objects.count()}")
    print(f"Marcas: {Marca.objects.count()}")
    print(f"Asignaciones: {AsignacionMarcaVendedor.objects.count()}")
    
    # Mostrar asignaciones por proveedor
    for proveedor in Proveedor.objects.all():
        marcas = Marca.objects.filter(asignaciones__proveedor=proveedor)
        print(f"{proveedor.nombre}: {list(marcas.values_list('nombre', flat=True))}")

if __name__ == '__main__':
    create_test_data()