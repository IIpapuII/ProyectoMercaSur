# -*- coding: utf-8 -*-
# tu_app/signals.py  (Asegúrate que el nombre del archivo sea signals.py)

from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.core.exceptions import ObjectDoesNotExist
# Importaciones necesarias de django-celery-beat
from django_celery_beat.models import PeriodicTask, CrontabSchedule, IntervalSchedule
import json # Para guardar args/kwargs como JSON en PeriodicTask

# Importa tu modelo EnvioProgramado (ajusta la ruta si es necesario)
# Ejemplo: from .models import EnvioProgramado
from .models import CorreoEnviado

# --- ¡¡IMPORTANTE!! Define el nombre completo de tu tarea de procesamiento ---
# Debe coincidir exactamente con el nombre registrado por Celery (usualmente 'nombre_app.tasks.nombre_funcion')
# Reemplaza 'tu_app' con el nombre real de tu aplicación Django.
TASK_NAME_PROCESAR_ENVIO = 'tu_app.tasks.procesar_y_enviar_correo_task'

@receiver(post_save, sender=CorreoEnviado)
def crear_o_actualizar_tarea_periodica_signal(sender, instance, created, **kwargs):
    """
    Signal Receiver: Se ejecuta después de guardar una instancia de EnvioProgramado.
    Crea o actualiza la PeriodicTask correspondiente en django-celery-beat.
    """
    print(f"--- Signal post_save detectado para EnvioProgramado ID: {instance.pk} ---")

    # Determinar el schedule (Crontab o Intervalo)
    schedule = instance.crontab if instance.crontab else instance.intervalo
    # La tarea en Celery Beat debe estar habilitada solo si el EnvioProgramado está activo Y tiene un schedule definido
    task_enabled = instance.activo and schedule is not None

    # Usar el nombre único definido en el modelo para la PeriodicTask
    task_name = instance.nombre_tarea
    if not task_name:
        print(f"⚠️ Advertencia: EnvioProgramado ID {instance.pk} no tiene 'nombre_tarea'. No se puede crear/actualizar PeriodicTask.")
        # Podrías marcar el estado como ERROR_CONFIG aquí si lo deseas
        # EnvioProgramado.objects.filter(pk=instance.pk).update(estado='ERROR_CONFIG')
        return

    try:
        # Intenta obtener o crear la PeriodicTask usando el nombre único
        periodic_task, task_created = PeriodicTask.objects.get_or_create(
            name=task_name,
            defaults={ # Valores por defecto si se crea una nueva
                'task': TASK_NAME_PROCESAR_ENVIO,
                'enabled': task_enabled,
                # Argumentos para la tarea: siempre pasar una lista o tupla
                'args': json.dumps([instance.pk]),
                'crontab': instance.crontab,
                'interval': instance.intervalo,
                'description': f'Envío programado: {instance.asunto[:50]}...' # Descripción útil
                # Puedes añadir kwargs si tu tarea los necesita:
                # 'kwargs': json.dumps({'configuracion_id': instance.pk}),
                # Otros campos opcionales: expires, one_off, start_time, etc.
            }
        )

        # Si la tarea ya existía, actualiza sus propiedades
        if not task_created:
            print(f"Actualizando PeriodicTask existente: {task_name}")
            # Compara y actualiza solo si hay cambios para evitar escrituras innecesarias
            updated_fields = []
            if periodic_task.task != TASK_NAME_PROCESAR_ENVIO:
                periodic_task.task = TASK_NAME_PROCESAR_ENVIO
                updated_fields.append('task')
            if periodic_task.enabled != task_enabled:
                periodic_task.enabled = task_enabled
                updated_fields.append('enabled')
            if periodic_task.args != json.dumps([instance.pk]):
                periodic_task.args = json.dumps([instance.pk])
                updated_fields.append('args')
            if periodic_task.crontab != instance.crontab:
                periodic_task.crontab = instance.crontab
                updated_fields.append('crontab')
            if periodic_task.interval != instance.intervalo:
                periodic_task.interval = instance.intervalo
                updated_fields.append('interval')

            new_description = f'Envío programado: {instance.asunto[:50]}...'
            if periodic_task.description != new_description:
                 periodic_task.description = new_description
                 updated_fields.append('description')

            # Solo guarda si hubo cambios
            if updated_fields:
                periodic_task.save(update_fields=updated_fields)
                print(f"PeriodicTask {task_name} actualizada. Campos: {', '.join(updated_fields)}")
            else:
                print(f"PeriodicTask {task_name} sin cambios necesarios.")

        else:
            print(f"Nueva PeriodicTask '{task_name}' creada.")

        # Actualizar la referencia en la instancia EnvioProgramado si cambió o es nueva
        # Usamos .update() para evitar llamar a post_save de nuevo y crear un bucle
        if instance.periodic_task != periodic_task:
             CorreoEnviado.objects.filter(pk=instance.pk).update(periodic_task=periodic_task)
             print(f"Referencia a PeriodicTask actualizada en EnvioProgramado ID: {instance.pk}")

        # Actualizar el estado de la configuración (ACTIVO/INACTIVO) si cambió
        current_status = 'ACTIVO' if task_enabled else 'INACTIVO'
        if instance.estado != current_status and instance.estado != 'ERROR_CONFIG':
             CorreoEnviado.objects.filter(pk=instance.pk).update(estado=current_status)
             print(f"Estado de EnvioProgramado ID {instance.pk} actualizado a {current_status}.")

    except Exception as e:
        # Captura cualquier error durante la creación/actualización de la tarea periódica
        print(f"❌ ERROR al crear/actualizar PeriodicTask para '{task_name}' (Envio ID {instance.pk}): {e}")
        # Marcar la configuración con error para revisión manual
        # Es importante evitar el bucle de save aquí también
        try:
            # Intenta actualizar solo el estado y limpiar la referencia a periodic_task
            CorreoEnviado.objects.filter(pk=instance.pk, estado__ne='ERROR_CONFIG').update(
                estado='ERROR_CONFIG',
                periodic_task=None
            )
        except Exception as e_update:
             print(f"❌ ERROR adicional al intentar marcar EnvioProgramado ID {instance.pk} como ERROR_CONFIG: {e_update}")


@receiver(post_delete, sender=CorreoEnviado)
def eliminar_tarea_periodica_signal(sender, instance, **kwargs):
    """
    Signal Receiver: Se ejecuta después de eliminar una instancia de EnvioProgramado.
    Elimina la PeriodicTask correspondiente de django-celery-beat.
    """
    print(f"--- Signal post_delete detectado para EnvioProgramado ID: {instance.pk}, Nombre Tarea: {instance.nombre_tarea} ---")

    # Usa el nombre único que debería estar guardado
    task_name = instance.nombre_tarea
    if not task_name:
        print("⚠️ Advertencia: No se puede eliminar PeriodicTask porque 'nombre_tarea' está vacío.")
        return

    try:
        # Busca la tarea periódica por su nombre único y la elimina
        periodic_task = PeriodicTask.objects.get(name=task_name)
        periodic_task.delete()
        print(f"PeriodicTask '{task_name}' eliminada exitosamente.")
    except PeriodicTask.DoesNotExist:
        # Si no existe (quizás nunca se creó o ya se borró), no hagas nada.
        print(f"No se encontró PeriodicTask con nombre '{task_name}' para eliminar (puede que ya no exista).")
    except Exception as e:
        # Captura otros posibles errores durante la eliminación
        print(f"❌ ERROR al intentar eliminar PeriodicTask '{task_name}': {e}")

