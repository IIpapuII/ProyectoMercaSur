from django.contrib import admin
from .models import SugeridoLinea


# ─────────────────────────────────────────────────────────────────────
# Filtros personalizados
# ─────────────────────────────────────────────────────────────────────
class MarcaEnLoteFilter(admin.SimpleListFilter):
    title = "Marca"
    parameter_name = "marca__id__exact"

    def lookups(self, request, model_admin):
        lote_id = request.GET.get("lote__id__exact")
        if lote_id:
            rows = (
                SugeridoLinea.objects
                .filter(lote_id=lote_id, marca__isnull=False)
                .values_list("marca_id", "marca__nombre")
                .distinct()
                .order_by("marca__nombre")
            )
        else:
            # Fallback: limitar a lo presente en el queryset actual del admin
            qs = model_admin.get_queryset(request).filter(marca__isnull=False)
            rows = qs.values_list("marca_id", "marca__nombre").distinct().order_by("marca__nombre")
        return [(mid, name) for mid, name in rows]

    def queryset(self, request, qs):
        val = self.value()
        if val:
            return qs.filter(marca_id=val)
        return qs


# NUEVO: base para filtros de valores distintos dentro del lote
class _BaseEnLoteDistinctFilter(admin.SimpleListFilter):
    title = ""
    parameter_name = ""
    field_name = ""

    def lookups(self, request, model_admin):
        qs = model_admin.get_queryset(request)
        lote_id = request.GET.get("lote__id__exact")
        if lote_id:
            qs = qs.filter(lote_id=lote_id)
        # excluir null/vacío
        qs = qs.exclude(**{f"{self.field_name}__isnull": True}).exclude(**{self.field_name: ""})
        vals = qs.values_list(self.field_name, flat=True).distinct().order_by(self.field_name)
        return [(v, v) for v in vals]

    def queryset(self, request, queryset):
        val = self.value()
        if val:
            return queryset.filter(**{self.field_name: val})
        return queryset

class NombreAlmacenEnLoteFilter(_BaseEnLoteDistinctFilter):
    title = "Almacén"
    parameter_name = "nombre_almacen__exact"
    field_name = "nombre_almacen"

class FamiliaEnLoteFilter(_BaseEnLoteDistinctFilter):
    title = "Familia"
    parameter_name = "familia__exact"
    field_name = "familia"

class SubfamiliaEnLoteFilter(_BaseEnLoteDistinctFilter):
    title = "Subfamilia"
    parameter_name = "subfamilia__exact"
    field_name = "subfamilia"

class ClasificacionEnLoteFilter(_BaseEnLoteDistinctFilter):
    title = "Clasificación"
    parameter_name = "clasificacion__exact"
    field_name = "clasificacion"

class EstadoLineaEnLoteFilter(_BaseEnLoteDistinctFilter):
    title = "Estado línea"
    parameter_name = "estado_linea__exact"
    field_name = "estado_linea"

