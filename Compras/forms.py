# forms.py
from .models import ArticuloClasificacionProcesado
from django import forms

class NuevaClasificacionForm(forms.ModelForm):
    class Meta:
        model = ArticuloClasificacionProcesado
        fields = ['nueva_clasificacion']
        widgets = {
            'nueva_clasificacion': forms.TextInput(attrs={
                'class': 'vTextField',
                'style': 'width:4em;text-align:center;'
            }),
        }
        labels = {
            'nueva_clasificacion': 'Nueva clasificación'
        }