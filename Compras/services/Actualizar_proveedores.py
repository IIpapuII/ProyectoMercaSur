from appMercaSur.conect import conectar_sql_server, ejecutar_consulta
from ..models import Proveedor, Marca, VendedorPerfil, AsignacionMarcaVendedor
from django.db import transaction
from django.contrib.auth.models import Group


def actualizar_proveedores_desde_icg() -> dict:
    """
    Actualiza proveedores y marcas desde ICG.
    Crea asignaciones de marca-vendedor para usuarios del grupo perfil_interno.
    Retorna dict con estadísticas del proceso.
    """
    consulta = """
WITH ProveedorMarca AS (
    SELECT 
        p.CODPROVEEDOR      AS CodProveedor,
        p.NOMPROVEEDOR      AS Proveedor,
        MC.DESCRIPCION      AS Marca
    FROM ARTICULOS AR
    INNER JOIN REFERENCIASPROV r 
        ON r.CODARTICULO = AR.CODARTICULO
    INNER JOIN PROVEEDORES p  
        ON p.CODPROVEEDOR = r.CODPROVEEDOR
    LEFT JOIN MARCA MC
        ON AR.MARCA = MC.CODMARCA
    WHERE AR.DESCATALOGADO = 'F'
)
SELECT DISTINCT
    CodProveedor,
    Proveedor,
    Marca
FROM ProveedorMarca
ORDER BY Proveedor, Marca;
"""
    
    # Conectar a SQL Server
    conexion = conectar_sql_server()
    if conexion is None or isinstance(conexion, str):
        error_msg = f"Error de conexión: {conexion}" if isinstance(conexion, str) else "No se pudo conectar a ICG"
        return {"success": False, "mensaje": error_msg}
    
    try:
        df = ejecutar_consulta(conexion, consulta)
    finally:
        try:
            if hasattr(conexion, "close"):
                conexion.close()
        except Exception:
            pass
    
    if df is None or df.empty:
        return {"success": False, "mensaje": "No se obtuvieron datos de ICG"}
    
    # Procesar datos
    proveedores_creados = 0
    marcas_creadas = 0
    proveedores_actualizados = 0
    asignaciones_creadas = 0
    
    with transaction.atomic():
        # Obtener proveedores existentes
        proveedores_existentes = {
            p.nombre: p for p in Proveedor.objects.all()
        }
        
        # Obtener marcas existentes
        marcas_existentes = {
            m.nombre: m for m in Marca.objects.all()
        }
        
        # Obtener vendedores del grupo perfil_interno
        try:
            grupo_interno = Group.objects.get(name="perfil_interno")
            usuarios_internos = grupo_interno.user_set.all()
            vendedores = VendedorPerfil.objects.filter(user__in=usuarios_internos)
        except Group.DoesNotExist:
            vendedores = VendedorPerfil.objects.none()
        
        # Procesar cada registro
        proveedores_vistos = set()
        marcas_vistas = set()
        nuevas_marcas = {}
        nuevos_proveedores = {}
        
        for _, row in df.iterrows():
            cod_prov = str(row.get("CodProveedor", "")).strip()
            nombre_prov = str(row.get("Proveedor", "")).strip()
            nombre_marca = str(row.get("Marca", "")).strip() if row.get("Marca") else None
            
            # Procesar proveedor
            if nombre_prov and nombre_prov not in proveedores_vistos:
                proveedores_vistos.add(nombre_prov)
                
                if nombre_prov in proveedores_existentes:
                    # Actualizar cod_icg si cambió
                    proveedor = proveedores_existentes[nombre_prov]
                    if proveedor.cod_icg != cod_prov:
                        proveedor.cod_icg = cod_prov
                        proveedor.save(update_fields=["cod_icg"])
                        proveedores_actualizados += 1
                else:
                    # Crear nuevo proveedor
                    proveedor = Proveedor.objects.create(
                        nombre=nombre_prov,
                        cod_icg=cod_prov,
                        nit="",
                        email_contacto="",
                        activo=True
                    )
                    proveedores_creados += 1
                    nuevos_proveedores[nombre_prov] = proveedor
            
            # Procesar marca
            if nombre_marca and nombre_marca not in marcas_vistas:
                marcas_vistas.add(nombre_marca)
                
                if nombre_marca not in marcas_existentes:
                    marca = Marca.objects.create(nombre=nombre_marca)
                    marcas_creadas += 1
                    nuevas_marcas[nombre_marca] = marca
                    marcas_existentes[nombre_marca] = marca
        
        # Crear asignaciones automáticas para proveedores y marcas nuevos
        if vendedores.exists() and (nuevos_proveedores or nuevas_marcas):
            # Obtener todas las combinaciones proveedor-marca del DF
            relaciones = set()
            for _, row in df.iterrows():
                nombre_prov = str(row.get("Proveedor", "")).strip()
                nombre_marca = str(row.get("Marca", "")).strip() if row.get("Marca") else None
                if nombre_prov and nombre_marca:
                    relaciones.add((nombre_prov, nombre_marca))
            
            # Obtener asignaciones existentes
            asignaciones_existentes = set(
                AsignacionMarcaVendedor.objects.values_list(
                    "proveedor__nombre", "marca__nombre", "vendedor_id"
                )
            )
            
            # Crear asignaciones nuevas
            asignaciones_nuevas = []
            for nombre_prov, nombre_marca in relaciones:
                proveedor = proveedores_existentes.get(nombre_prov) or nuevos_proveedores.get(nombre_prov)
                marca = marcas_existentes.get(nombre_marca)
                
                if not proveedor or not marca:
                    continue
                
                for vendedor in vendedores:
                    # Verificar si ya existe
                    if (nombre_prov, nombre_marca, vendedor.id) not in asignaciones_existentes:
                        asignaciones_nuevas.append(
                            AsignacionMarcaVendedor(
                                proveedor=proveedor,
                                marca=marca,
                                vendedor=vendedor
                            )
                        )
            
            if asignaciones_nuevas:
                AsignacionMarcaVendedor.objects.bulk_create(asignaciones_nuevas, ignore_conflicts=True)
                asignaciones_creadas = len(asignaciones_nuevas)
    
    mensaje = (
        f"Proveedores: {proveedores_creados} creados, {proveedores_actualizados} actualizados. "
        f"Marcas: {marcas_creadas} creadas. "
        f"Asignaciones marca-vendedor: {asignaciones_creadas} creadas."
    )
    
    return {
        "success": True,
        "mensaje": mensaje,
        "proveedores_creados": proveedores_creados,
        "proveedores_actualizados": proveedores_actualizados,
        "marcas_creadas": marcas_creadas,
        "asignaciones_creadas": asignaciones_creadas
    }


