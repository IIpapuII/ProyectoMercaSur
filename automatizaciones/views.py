from django.shortcuts import render
from django.http import HttpResponseRedirect
from django.contrib import messages
from .form import CSVUploadForm
import pandas as pd
from .service.upload import update_or_create_articles, marcarArticulosComoNoModificados, articulosMoficados, send_modified_articles
# Create your views here.
from .tasks import procesar_articulos_task
def import_from_csv(request):
        """Importa datos desde un archivo CSV subido desde el Django Admin."""
        if request.method == "POST":
            form = CSVUploadForm(request.POST, request.FILES)
            if form.is_valid():
                try:
                    df = pd.read_csv(request.FILES["csv_file"])
                    update_or_create_articles(df)
                    messages.success(request, "✅ Importación desde CSV completada.")
                except Exception as e:
                    messages.error(request, f"⚠️ Error al importar desde CSV: {e}")
                return HttpResponseRedirect("../")
        else:
            form = CSVUploadForm()

        return render(request, "admin/import_csv.html", {"form": form})

def index(request):
    artoculos = articulosMoficados()
    #marcarArticulosComoNoModificados()
    procesar_articulos_task()
    send_modified_articles()
    context = {
        "articulos_modificados": artoculos
    }
    return render(request, "index.html", context )