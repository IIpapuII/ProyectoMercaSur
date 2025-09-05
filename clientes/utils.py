from django.db import transaction
from .models import SecuenciaCodCliente
from django.utils import timezone
from django.db.models import F



def generar_nuevo_codcliente():
    with transaction.atomic():
        # Crea el registro si no existe (y luego lo bloquea)
        obj, created = SecuenciaCodCliente.objects.get_or_create(
            pk=1,
            defaults={"ultimo_codigo": 0, "rango_maximo": 999999}
        )

        # Asegura el bloqueo de fila (si el engine lo soporta)
        obj = (
            SecuenciaCodCliente.objects
            .select_for_update()
            .get(pk=obj.pk)
        )

        # Incremento atómico con validación de rango (un solo statement)
        updated = (
            SecuenciaCodCliente.objects
            .filter(pk=obj.pk, ultimo_codigo__lt=F("rango_maximo"))
            .update(ultimo_codigo=F("ultimo_codigo") + 1)
        )
        if updated == 0:
            # No se actualizó: ya estabas en el máximo
            raise ValueError("Se ha alcanzado el límite de códigos disponibles.")

        # Leer el valor ya incrementado (sin carreras)
        obj.refresh_from_db(fields=["ultimo_codigo"])
        return obj.ultimo_codigo


def calcular_edad(fecha_nacimiento):
    """
    Calcula la edad en años a partir de una fecha de nacimiento usando timezone.now() de Django.
    
    Parámetros:
    - fecha_nacimiento (datetime.date): Fecha de nacimiento de la persona.

    Retorna:
    - int: Edad actual de la persona en años.
    """
    hoy = timezone.now().date()
    edad = hoy.year - fecha_nacimiento.year

    if (hoy.month, hoy.day) < (fecha_nacimiento.month, fecha_nacimiento.day):
        edad -= 1

    return edad

def bool_a_tf(valor_bool):
    """
    Convierte un valor booleano a 'T' o 'F'.
    """
    return 'T' if valor_bool else 'F'
