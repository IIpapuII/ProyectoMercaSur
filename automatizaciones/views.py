from django.shortcuts import render
from django.http import HttpResponseRedirect
from django.contrib import messages
from .form import CSVUploadForm
import pandas as pd
from .service.upload import * 
from .service.extraerApi import exportar_productos_basicos_excel
from .service.rappi_update_state import update_inventory_one_by_one, RappiError
from .service.rappi_missing import log_missing_product
from .service.rappi_auth import get_rappi_token
from clientes.tasks import generar_enviar_codigo_temporal

from django.conf import settings
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
    LOCAL_TO_NAME = {
        "900175315": "Mercasur, Caldas",
        "900175197": "Mercasur, Soto Mayor",
        "900175196": "Mercasur, Cabecera",
        "900174620": "Mercasur, Centro",
    }

    # nombre -> id interno de Rappi (del JSON que pasaste)
    NAME_TO_RAPPI = {
        "Mercasur, Centro": 21128,
        "Mercasur, Cabecera": 21243,
        "Mercasur, Soto Mayor": 21244,
        "Mercasur, Caldas": 21261,
    }

    server = settings.RAPPI_URL_BASE
    token = get_rappi_token()

    #articulo = Articulos.objects.get(ean="7707205550097")  # ejemplo
    #print("Actualizando artículo:", articulo)

    qs = Articulos.objects.all().order_by("store_id")

    results = []
    for art in qs:
        print("Actualizando artículo:", art.ean, "en tienda local", art.store_id)
        try:
            res = update_inventory_one_by_one(
                server=server,
                token=token,
                articulo=art,
                local_to_name=LOCAL_TO_NAME,
                name_to_rappi=NAME_TO_RAPPI,
            )
            results.append({"ean": art.ean, "store_id": art.store_id, "ok": True, "detail": res})
        except RappiError as e:
            err = str(e)
            if "No encontré IDs" in err or "no devolvió ni productId ni listingId" in err:
                store_name = LOCAL_TO_NAME.get(str(art.store_id).strip())
                rappi_store_id = NAME_TO_RAPPI.get(store_name)
                # si tu update_inventory_one_by_one devuelve 'lookups' en el dict de error, pásalo aquí
                log_missing_product(
                    articulo=art,
                    store_name=store_name,
                    rappi_store_id=rappi_store_id,
                    error=err,
                    lookups_debug=None,  # pon aquí el detalle si lo tienes
                )
            results.append({"ean": art.ean, "store_id": art.store_id, "ok": False, "error": str(e)})
    #articulosModificadosTotal()
    #print("articulos modificados")
    #send_modified_articles()
    #actualizar_descuentos_task()
    #generar_enviar_codigo_temporal()
    #print("hola")
    
    context = {
        "articulos_modificados": []
    }
    return render(request, "index.html", context )