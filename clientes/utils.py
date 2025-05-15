from django.db import transaction
from .models import SecuenciaCodCliente

def generar_nuevo_codcliente():
    with transaction.atomic():
        secuencia, _ = SecuenciaCodCliente.objects.select_for_update().get_or_create(pk=1)
        
        nuevo_codigo = secuencia.ultimo_codigo + 1
        if nuevo_codigo > secuencia.rango_maximo:
            raise ValueError("Se ha alcanzado el límite de códigos disponibles.")

        secuencia.ultimo_codigo = nuevo_codigo
        secuencia.save()
        return nuevo_codigo