# inventarios/services/exports.py
from io import BytesIO
from django.template.loader import render_to_string

def export_lines_to_xlsx(queryset, filename: str = "sugerido.xlsx"):
    """
    Export simple a XLSX usando openpyxl. Si no está instalado, cae a CSV.
    """
    try:
        from openpyxl import Workbook
    except ImportError:
        # fallback CSV
        import csv
        buffer = BytesIO()
        import codecs
        writer = csv.writer(codecs.getwriter("utf-8")(buffer), delimiter=";")
        writer.writerow(["Proveedor","Marca","Almacén","Código","Descripción","SugeridoCalc","SugeridoInterno","CostoUnit","CostoLinea"])
        for ln in queryset:
            writer.writerow([
                ln.proveedor, (ln.marca or ""), f"{ln.cod_almacen}-{ln.nombre_almacen}",
                ln.codigo_articulo, ln.descripcion,
                ln.sugerido_calculado, ln.sugerido_interno, ln.ultimo_costo, ln.costo_linea
            ])
        return buffer.getvalue(), filename.replace(".xlsx", ".csv")

    wb = Workbook()
    ws = wb.active
    ws.title = "Sugerido"
    ws.append(["Proveedor","Marca","Almacén","Código","Descripción",
               "StockAct","StockMin","StockMax",
               "UdsBase","UdsMult","Embalaje",
               "CostoUnit","SugeridoBase","Factor","SugeridoCalc",
               "SugeridoInterno","Cajas","CostoLinea","Clasificación"])
    for ln in queryset:
        ws.append([
            ln.proveedor, (ln.marca or ""), f"{ln.cod_almacen}-{ln.nombre_almacen}",
            ln.codigo_articulo, ln.descripcion,
            ln.stock_actual, ln.stock_minimo, ln.stock_maximo,
            ln.uds_compra_base, ln.uds_compra_mult, ln.embalaje,
            ln.ultimo_costo, ln.sugerido_base, ln.factor_almacen,
            ln.sugerido_calculado, ln.sugerido_interno,
            ln.cajas_calculadas, ln.costo_linea, (ln.clasificacion or "")
        ])
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue(), filename


def render_orden_compra_pdf(encabezado: dict, lineas):
    """
    Genera un PDF simple con WeasyPrint si está instalado; si no, devuelve HTML.
    encabezado = {"numero_orden","proveedor","almacen","fecha","costo_total"}
    """
    html = render_to_string("inventarios/orden_compra.html", {
        "encabezado": encabezado,
        "lineas": lineas,
    })
    filename = f"orden_compra_{encabezado.get('numero_orden','OC')}.pdf"
    try:
        from weasyprint import HTML
        pdf_bytes = HTML(string=html).write_pdf()
        return pdf_bytes, filename
    except Exception:
        return html.encode("utf-8"), filename.replace(".pdf", ".html")
