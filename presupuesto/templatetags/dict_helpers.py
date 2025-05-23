# tu_app/templatetags/dict_helpers.py
from django import template
from django.template.defaultfilters import floatformat

register = template.Library()

@register.filter
def get_item(dictionary, key):
    """
    Permite acceder a un item de un diccionario usando una variable como clave
    en las plantillas Django. Uso: {{ mi_diccionario|get_item:mi_variable_clave }}
    Devuelve None si la clave no existe o el input no es un diccionario.
    """
    if isinstance(dictionary, dict):
        return dictionary.get(key)
    return None
