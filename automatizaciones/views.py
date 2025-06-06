from django.shortcuts import render
from django.http import HttpResponseRedirect
from django.contrib import messages
from .form import CSVUploadForm
import pandas as pd
from .service.upload import * 
from clientes.tasks import generar_enviar_codigo_temporal
# Create your views here.
from .tasks import procesar_articulos_task, procesar_articulos_parze_task,  actualizar_descuentos_task
def import_from_csv(request):
        """Importa datos desde un archivo CSV subido desde el Django Admin."""
        if request.method == "POST":
            form = CSVUploadForm(request.POST, request.FILES)
            if form.is_valid():
                try:
                    df = pd.read_csv(request.FILES["csv_file"])
                    update_or_create_articles(df)
                    messages.success(request, "Importación desde CSV completada.")
                except Exception as e:
                    messages.error(request, f"Error al importar desde CSV: {e}")
                return HttpResponseRedirect("../")
        else:
            form = CSVUploadForm()

        return render(request, "admin/import_csv.html", {"form": form})

def index(request):
    #actualizar_descuentos()
    #enviar_csv_a_api()
    #procesar_articulos_parze_task()
    #generar_csv_articulos_modificados()
    #procesar_articulos_task()
    #send_modified_articles()
    actualizar_descuentos_task()
    #generar_enviar_codigo_temporal()
    
    context = {
        "articulos_modificados": []
    }
    return render(request, "index.html", context )