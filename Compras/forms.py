# forms.py
from .models import ArticuloClasificacionProcesado, SugeridoLote, Marca, AsignacionMarcaVendedor
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

class SugeridoLoteAdminForm(forms.ModelForm):
    """Formulario personalizado para SugeridoLote que gestiona la dependencia proveedor -> marca (HTMX)"""

    class Meta:
        model = SugeridoLote
        fields = '__all__'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Filtrado inicial de marcas (edición vs creación)
        if self.instance and self.instance.pk and self.instance.proveedor:
            self.fields['marcas'].queryset = Marca.objects.filter(
                asignaciones__proveedor=self.instance.proveedor
            ).distinct()
        else:
            # Mostrar solo marcas que tienen asignación (para que HTMX reemplace bien después)
            self.fields['marcas'].queryset = Marca.objects.filter(
                asignaciones__isnull=False
            ).distinct()
        # Configuración más simple - JavaScript manejará Select2
        # Usar la vista normal en lugar del endpoint del admin
        api_url = '/admin/api/marcas-por-proveedor/'
        
        self.fields['proveedor'].widget.attrs.update({
            'data-marcas-url': api_url,
            'data-target-marca': 'id_marcas',
        })
        self.fields['marcas'].widget.attrs.update({
            'id': 'id_marcas'
        })
        # Forzar el ID también en el widget directamente
        self.fields['marcas'].widget.attrs['id'] = 'id_marcas'

        print("Formulario SugeridoLote configurado con endpoint personalizado para múltiples marcas")

    def clean(self):
        """Validación para asegurar que las marcas pertenezcan al proveedor."""
        cleaned_data = super().clean()
        proveedor = cleaned_data.get('proveedor')
        marcas = cleaned_data.get('marcas')

        if proveedor and marcas:
            for marca in marcas:
                ok = AsignacionMarcaVendedor.objects.filter(
                    proveedor=proveedor, marca=marca
                ).exists()
                if not ok:
                    raise forms.ValidationError(
                        f'La marca "{marca}" no está asignada al proveedor "{proveedor}". '
                        'Por favor seleccione marcas válidas para este proveedor.'
                    )
        return cleaned_data
    
    def _get_marcas_data_json(self):
        """DEPRECATED (usamos HTMX)"""
        import json
        return json.dumps({})