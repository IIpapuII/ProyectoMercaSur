# signals.py
from django.db.models.signals import m2m_changed
from django.dispatch import receiver
from .models import SugeridoLote


@receiver(m2m_changed, sender=SugeridoLote.marcas.through)
def importar_datos_al_asignar_marcas(sender, instance, action, **kwargs):
    """
    Signal que se ejecuta cuando se modifican las marcas de un lote.
    Importa los datos desde ICG cuando se agregan marcas a un lote nuevo.
    """
    # Solo procesar cuando se agregan marcas (post_add) y el lote está marcado para importación
    if action == 'post_add' and hasattr(instance, '_pending_import') and instance._pending_import:
        # Limpiar el flag
        instance._pending_import = False
        
        # Obtener las marcas asignadas
        marcas_seleccionadas = list(instance.marcas.all())
        
        if marcas_seleccionadas and instance.proveedor:
            from Compras.services.icg_import import import_data_sugerido_inventario
            
            # Extraer nombres de las marcas
            nombres_marcas = [m.nombre for m in marcas_seleccionadas]
            
            print(f"🔄 Importando datos para lote {instance.id} con marcas: {nombres_marcas}")
            
            import_data_sugerido_inventario(
                user_id=instance.creado_por_id,
                marcas=nombres_marcas,
                lote_id=instance.pk,
                provedor=instance.proveedor.nombre
            )
            
            # Notificar vendedor asignado para cada marca
            try:
                from Compras.services.notifications import notificar_vendedor_lote_asignado
                for marca in marcas_seleccionadas:
                    try:
                        notificar_vendedor_lote_asignado(
                            proveedor=instance.proveedor,
                            marca=marca,
                            lote=instance
                        )
                    except Exception as e:
                        print(f"Error notificando para marca {marca}: {e}")
            except Exception as e:
                print(f"Error en notificaciones: {e}")
            
            # Recalcular totales y actualizar estado
            instance.recalcular_totales()
            
            nuevo_estado = SugeridoLote.Estado.ENVIADO if instance.total_lineas > 0 else SugeridoLote.Estado.PENDIENTE
            if instance.estado != nuevo_estado:
                instance.estado = nuevo_estado
            
            # Guardar cambios
            SugeridoLote.objects.filter(pk=instance.pk).update(
                total_lineas=instance.total_lineas,
                total_costo=instance.total_costo,
                estado=instance.estado
            )
            
            print(f"✅ Importación completada: {instance.total_lineas} líneas, estado: {instance.estado}")
