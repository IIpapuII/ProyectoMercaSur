
from django.shortcuts import render, redirect, get_object_or_404
from formtools.wizard.views import SessionWizardView
from .models import ProcesoClasificacion, ArticuloClasificacionTemporal
from .forms import NuevaClasificacionForm
from django.forms import modelformset_factory
from django.utils.decorators import method_decorator
from django.contrib.admin.views.decorators import staff_member_required


@method_decorator(staff_member_required, name='dispatch')
class ClasificacionWizard(SessionWizardView):
    TEMPLATES = {
        "step1": "wizard/step1.html",
        "step2": "wizard/step2.html",
        "step3": "wizard/step3.html",
    }

    def get_template_names(self):
        return [self.TEMPLATES[self.steps.current]]

    def get_form(self, step=None, data=None, files=None):
        if step == "step2":
            proceso = ProcesoClasificacion.objects.filter(estado='procesado').order_by('-fecha_inicio').first()
            queryset = ArticuloClasificacionTemporal.objects.filter(proceso=proceso)
            NuevaClasificacionFormSet = modelformset_factory(
                ArticuloClasificacionTemporal,
                form=NuevaClasificacionForm,
                extra=0
            )
            # Para POST, debes pasar data; para GET, no.
            if data:
                return NuevaClasificacionFormSet(queryset=queryset, data=data)
            return NuevaClasificacionFormSet(queryset=queryset)
        return super().get_form(step, data, files)

    def render_next_step(self, form, **kwargs):
        # Si es formset, lo pasa bien al template
        return self.render(form, **kwargs)

    def get_context_data(self, form, **kwargs):
        context = super().get_context_data(form=form, **kwargs)
        if self.steps.current == "step3":
            proceso = ProcesoClasificacion.objects.filter(estado='procesado').order_by('-fecha_inicio').first()
            context['proceso'] = proceso
            context['articulos'] = proceso.articulos_temporales.all()
        return context

    def done(self, form_list, **kwargs):
        # Guardar los cambios del formset del step2 antes de terminar
        proceso = ProcesoClasificacion.objects.filter(estado='procesado').order_by('-fecha_inicio').first()
        if proceso:
            # Guardar los datos editados en step2
            formset = self.get_form(step='step2', data=self.storage.get_step_data('step2'))
            if formset.is_valid():
                formset.save()
            proceso.estado = 'confirmado'
            proceso.save()
        return render(self.request, "wizard/finish.html", {'proceso': proceso})
