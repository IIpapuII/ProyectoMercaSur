# forms.py
from .models import ArticuloClasificacionProcesado
from django import forms

class NuevaClasificacionForm(forms.ModelForm):
    class Meta:
        model = ArticuloClasificacionProcesado
        fields = ['id', 'codigo', 'descripcion', 'clasificacion_actual', 'nueva_clasificacion']
        widgets = {
            'codigo': forms.TextInput(attrs={'readonly': 'readonly'}),
            'descripcion': forms.TextInput(attrs={'readonly': 'readonly'}),
            'clasificacion_actual': forms.TextInput(attrs={'readonly': 'readonly'}),
        }
