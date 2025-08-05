from django import forms
from .models import Sede, CategoriaVenta # Importa los modelos necesarios
from decimal import Decimal
from datetime import date
from django.forms import formset_factory
from .models import CategoriaVenta, Sede 

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
        queryset=Sede.objects.none(),
        label="Seleccione Sede",
        empty_label="--Ninguna sede permitida--",
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    categoria = forms.ModelChoiceField(
        queryset=CategoriaVenta.objects.none(),
        label="Seleccione Categoría",
        empty_label=None,
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
    def __init__(self, *args, **kwargs):
        # Extraemos el usuario que pasamos desde la vista
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)

        if user:
            if user.groups.filter(name='Acceso Total Sedes').exists() or user.is_superuser:
                queryset_sedes = Sede.objects.all().order_by('nombre')
            else:
                # Obtenemos la lista de nombres de los grupos del usuario.
                nombres_de_grupos = user.groups.values_list('name', flat=True)
                queryset_sedes = Sede.objects.filter(nombre__in=nombres_de_grupos).order_by('nombre')

            # Asignamos el queryset filtrado al campo 'sede'
            self.fields['sede'].queryset = queryset_sedes

            if queryset_sedes.exists():
                self.fields['sede'].empty_label = None

            # Filtrar categorías según el perfil del usuario
            perfil = getattr(user, 'perfil', None)
            if perfil:
                categorias_permitidas = perfil.categorias_permitidas.all().order_by('nombre')
            else:
                categorias_permitidas = CategoriaVenta.objects.none()
            self.fields['categoria'].queryset = categorias_permitidas

class FiltroRangoFechasForm(forms.Form):
    fecha_inicio = forms.DateField(
        required=True,
        widget=forms.DateInput(attrs={'type': 'date','class': 'form-control'}),
        label="Desde"
    )
    fecha_fin = forms.DateField(
        required=True,
        widget=forms.DateInput(attrs={'type': 'date','class': 'form-control'}),
        label="Hasta"
    )
    categoria = forms.ModelChoiceField(
        queryset=CategoriaVenta.objects.none(),
        label="Seleccione Categoría",
        empty_label=None, 
        widget=forms.Select(attrs={'class': 'form-control'})
    )

    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        if user:
            perfil = getattr(user, 'perfil', None)
            if perfil:
                categorias_permitidas = perfil.categorias_permitidas.all().order_by('nombre')
            else:
                categorias_permitidas = CategoriaVenta.objects.none()
            self.fields['categoria'].queryset = categorias_permitidas