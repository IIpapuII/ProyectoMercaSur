from django.db import transaction
from .models import SecuenciaCodCliente
from django.utils import timezone


def generar_nuevo_codcliente():
    with transaction.atomic():
        secuencia, _ = SecuenciaCodCliente.objects.select_for_update().get_or_create(pk=1)
        
        nuevo_codigo = secuencia.ultimo_codigo + 1
        if nuevo_codigo > secuencia.rango_maximo:
            raise ValueError("Se ha alcanzado el límite de códigos disponibles.")

        secuencia.ultimo_codigo = nuevo_codigo
        secuencia.save()
        return nuevo_codigo

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
