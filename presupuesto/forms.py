from django import forms
from .models import Sede, CategoriaVenta # Importa los modelos necesarios
from decimal import Decimal
from datetime import date
from django.forms import formset_factory

class SedeAñoMesForm(forms.Form):
    """Formulario para seleccionar la Sede, Año y Mes."""
    sede = forms.ModelChoiceField(
        queryset=Sede.objects.all().order_by('nombre'),
        empty_label=None,
        label="Seleccione Sede",
        widget=forms.Select(attrs={'class': 'form-control'}) # Ejemplo de clase CSS
    )
    anio = forms.IntegerField(
        min_value=2000,
        max_value=2100,
        initial=date.today().year,
        label="Año",
        widget=forms.NumberInput(attrs={'class': 'form-control'})
    )
    mes = forms.IntegerField(
        min_value=1,
        max_value=12,
        initial=date.today().month,
        label="Mes",
        widget=forms.NumberInput(attrs={'class': 'form-control', 'min': '1', 'max': '12'})
    )

class PresupuestoCategoriaForm(forms.Form):
    """Formulario para ingresar el presupuesto de UNA categoría."""
    # Usaremos un campo oculto o de solo lectura para identificar la categoría
    # si es necesario pasarla explícitamente, aunque a menudo se maneja por índice.
    # categoria_id = forms.IntegerField(widget=forms.HiddenInput(), required=False)
    # categoria_nombre = forms.CharField(widget=forms.TextInput(attrs={'readonly': 'readonly'}), required=False)

    presupuesto = forms.DecimalField(
        max_digits=15,
        decimal_places=2,
        required=False, # Permitir vacío (se tratará como 0)
        label="", # El label se pondrá dinámicamente en la plantilla
        widget=forms.NumberInput(attrs={'step': '0.01', 'placeholder': '0.00', 'class': 'form-control form-control-sm'})
    )

# Crear el Formset que agrupa múltiples PresupuestoCategoriaForm
# extra=0 significa que no se mostrarán formularios vacíos adicionales por defecto.
PresupuestoCategoriaFormSet = formset_factory(PresupuestoCategoriaForm, extra=0)

class FiltroCumplimientoForm(forms.Form):
    sede = forms.ModelChoiceField(
        queryset=Sede.objects.all().order_by('nombre'),
        label="Seleccione Sede",
        empty_label=None, # Forzar selección
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    # Hacer la categoría opcional, si no se selecciona, se podrían mostrar todas o un resumen.
    # Por ahora, la haremos obligatoria para simplificar la tabla de resultados a una categoría.
    categoria = forms.ModelChoiceField(
        queryset=CategoriaVenta.objects.all().order_by('nombre'),
        label="Seleccione Categoría",
        empty_label=None, # Forzar selección. Puedes cambiarlo si quieres un "Todas las Categorías".
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    anio = forms.IntegerField(
        min_value=2000, max_value=2100,
        initial=date.today().year,
        label="Año",
        widget=forms.NumberInput(attrs={'class': 'form-control'})
    )
    mes = forms.IntegerField(
        min_value=1, max_value=12,
        initial=date.today().month,
        label="Mes",
        widget=forms.NumberInput(attrs={'class': 'form-control', 'min':'1', 'max':'12'})
    )