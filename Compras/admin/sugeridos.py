from django.contrib import admin
from django.urls import path, reverse
from django.utils.html import format_html
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect
from django.http import HttpResponse
from django.db.models import Sum, Count, Case, When, F, Q, DecimalField, Exists, OuterRef
from django.db.models.functions import Coalesce
from django.db import transaction
from django.utils import timezone
from django import forms
from decimal import Decimal
from datetime import datetime
import csv
import json
from django.template.loader import render_to_string

# Importaciones locales
from ..models import (
    SugeridoLote,
    SugeridoLinea,
    AsignacionMarcaVendedor,
    Proveedor,
    Marca
)
from ..services.notifications import (
    notificar_proveedor_lote_enviado,
    notificar_compras_respuesta_proveedor
)
from ..services.exports import export_lines_to_xlsx
from ..services.kpi_proveedores import calcular_cumplimiento_presupuesto
from django.http import HttpResponse, HttpResponseBadRequest
from ..services.icg_integration import  enviar_orden_a_icg
from ..services.icg_pedidos import crear_pedido_compra_desde_lote
from ..forms import SugeridoLoteAdminForm


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


# ─────────────────────────────
# Inlines / Admins
# ─────────────────────────────

class SugeridoLineaInline(admin.TabularInline):
    model = SugeridoLinea
    extra = 0
    fields = (
       "nombre_almacen", "proveedor", "marca",
        "codigo_articulo", "descripcion",
        "stock_actual", "stock_minimo", "stock_maximo",
        "embalaje",
        "ultimo_costo",
        "sugerido_base",  "sugerido_calculado", "cajas_calculadas",
        "sugerido_interno",
        "costo_linea",
        "clasificacion", "warning_no_multiplo", "warning_incremento_100",
        "estado_linea",
    )
    readonly_fields = (
        "nombre_almacen", "proveedor", "marca",
        "codigo_articulo", "descripcion",
        "stock_actual", "stock_minimo", "stock_maximo",
        "embalaje",
        "ultimo_costo",
        "sugerido_base",  "sugerido_calculado", "cajas_calculadas",
        "costo_linea",
        "clasificacion", "warning_no_multiplo", "warning_incremento_100",
        "estado_linea",
    )


# ─────────────────────────────────────────────────────────────────────
# Admin Lote (con link a "ver líneas del lote")
# ─────────────────────────────────────────────────────────────────────

@admin.register(SugeridoLote)
class SugeridoLoteAdmin(admin.ModelAdmin):
    form = SugeridoLoteAdminForm
    change_form_template = "admin/compras/sugeridolote/change_form.html"
    list_display = ("id", "nombre", "fecha_extraccion", "estado",
                    "total_lineas", "total_costo", "creado_por", "ver_lineas")
    list_filter = ("estado", "creado_por",)
    search_fields = ("nombre", "id", "creado_por__username")
    date_hierarchy = "fecha_extraccion"
    readonly_fields = ("total_lineas","total_costo", "fecha_extraccion", "estado", 
                       "clasificacion_filtro","numserie","numpedido","subserie","pedidos_icg","creado_por",)
    fields = ("nombre", "proveedor", "marca", "observaciones")  # Orden específico: proveedor primero, luego marca
    actions = [
        "accion_enviar_a_proveedor",
        "accion_marcar_confirmado",
        "accion_marcar_completado",
        "accion_exportar_xlsx",
        "accion_recalcular_totales",
        "accion_anular_lote",
        "accion_reabrir_proveedor",
    ]

    @admin.display(description="Ver líneas")
    def ver_lineas(self, obj: SugeridoLote):
        url = reverse("admin:sugeridolinea_por_lote", args=[obj.id])
        return format_html(
            '<a class="button" style="background-color: #28a745; color: white; padding: 5px 10px; '
            'border-radius: 5px; text-decoration: none;" href="{}">Abrir Detalle</a>',
            url
        )

    @admin.action(description="Enviar a proveedor")
    def accion_enviar_a_proveedor(self, request, qs):
        from ..models import SugeridoLote  # importar para evitar problemas de circular import
        enviados = 0
        for lote in qs:
            if lote.estado == SugeridoLote.Estado.BORRADOR:
                lote.estado = SugeridoLote.Estado.ENVIADO
                lote.save(update_fields=['estado'])
                # Notificar por email
                try:
                    notificar_proveedor_lote_enviado(lote)
                except Exception as e:
                    messages.warning(request, f"Error al enviar notificación para lote {lote.id}: {e}")
                enviados += 1
        if enviados:
            self.message_user(request, f"{enviados} lote(s) enviado(s) a proveedor.", messages.SUCCESS)
        else:
            self.message_user(request, "No hay lotes en BORRADOR para enviar.", messages.INFO)
    
    @admin.action(description="Marcar como CONFIRMADO")
    def accion_marcar_confirmado(self, request, qs):
        n = qs.update(estado=SugeridoLote.Estado.CONFIRMADO)
        self.message_user(request, f"{n} lote(s) marcados como CONFIRMADO.", messages.SUCCESS)

    @admin.action(description="Marcar como COMPLETADO")
    def accion_marcar_completado(self, request, qs):
        n = qs.update(estado=SugeridoLote.Estado.COMPLETADO)
        self.message_user(request, f"{n} lote(s) marcados como COMPLETADO.", messages.SUCCESS)
    
    @admin.action(description="Anular Lote")
    def accion_anular_lote(self, request, qs):
        n = qs.update(estado=SugeridoLote.Estado.ANULADO)
        self.message_user(request, f"{n} lote(s) anulados.", messages.SUCCESS)
    
    @admin.action(description="Reabrir proveedor")
    def accion_reabrir_proveedor(self, request, qs):
        bloqueados = qs.filter(estado=SugeridoLote.Estado.COMPLETADO).count()
        actualizados = qs.exclude(estado=SugeridoLote.Estado.COMPLETADO)\
                         .update(estado=SugeridoLote.Estado.ENVIADO)
        if actualizados:
            self.message_user(request, f"{actualizados} lote(s) reabiertos para proveedor.", messages.SUCCESS)
        if bloqueados:
            self.message_user(request, f"{bloqueados} lote(s) no se pueden reabrir porque están en estado COMPLETADO.", messages.WARNING)

    @admin.action(description="Exportar XLSX (lote)")
    def accion_exportar_xlsx(self, request, qs):
        if not qs.exists():
            self.message_user(request, "Selecciona al menos un lote.", messages.WARNING)
            return

        if qs.count() == 1:
            lote = qs.first()
            lineas = SugeridoLinea.objects.filter(lote=lote).select_related("proveedor", "marca", "vendedor")
            filename = f"sugerido_lote_{lote.id}.xlsx"
        else:
            ids = list(qs.values_list("id", flat=True))
            lineas = SugeridoLinea.objects.filter(lote_id__in=ids).select_related("proveedor", "marca", "vendedor")
            filename = "sugerido_lotes_" + "_".join(map(str, ids)) + ".xlsx"

        # ✅ No intentes mutar FKs a str aquí; el exportador hace la conversión segura
        xlsx_bytes, filename = export_lines_to_xlsx(lineas, filename=filename)

        resp = HttpResponse(
            xlsx_bytes,
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        resp["Content-Disposition"] = f'attachment; filename="{filename}"'
        return resp

    @admin.action(description="Recalcular totales")
    def accion_recalcular_totales(self, request, qs):
        actualizados = 0
        for lote in qs:
            lote.recalcular_totales()
            actualizados += 1
        self.message_user(request, f"{actualizados} lote(s) recalculados.", messages.SUCCESS)

    # Nuevo: setear creado_por automáticamente
    def save_model(self, request, obj, form, change):
        if not change or not getattr(obj, "creado_por_id", None):
            obj.creado_por = request.user
        super().save_model(request, obj, form, change)

    # NUEVO: detección robusta de perfiles
    def _get_perfil_proveedor_obj(self, request):
        perfil = getattr(request.user, "perfil_proveedor", None)
        try:
            if hasattr(perfil, "all"):
                return perfil.all().first()
            if hasattr(perfil, "exists") and hasattr(perfil, "model"):
                return perfil.first()
            return perfil
        except Exception:
            return None
    def _get_perfil_vendedor_obj(self, request):
        perfil = getattr(request.user, "perfil_vendedor", None)
        try:
            if hasattr(perfil, "all"):
                return perfil.all().first()
            if hasattr(perfil, "exists") and hasattr(perfil, "model"):
                return perfil.first()
            return perfil
        except Exception:
            return None

    def _es_proveedor(self, request) -> bool:
        """
        True si el usuario pertenece al grupo 'perfil_proveedor' o
        tiene un perfil_proveedor relacionado (aunque también sea interno).
        """
        en_grupo = request.user.groups.filter(name='perfil_proveedor').exists()
        tiene_perfil = self._get_perfil_proveedor_obj(request) is not None
        return en_grupo or tiene_perfil

    def get_actions(self, request):
        actions = super().get_actions(request)
        if self._es_proveedor(request):
            return {k: v for k, v in actions.items() if k == "accion_exportar_xlsx"}
        return actions

    # NUEVO: detectar vendedor interno
    def _es_vendedor(self, request) -> bool:
        return self._get_perfil_vendedor_obj(request) is not None

    # Nuevo: filtrar listado por asignaciones
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        perfil_prov = self._get_perfil_proveedor_obj(request)
        if perfil_prov:
            return qs.filter(proveedor=perfil_prov.proveedor)
        perfil_vend = self._get_perfil_vendedor_obj(request)
        if perfil_vend:
            return qs.filter(
                Exists(
                    AsignacionMarcaVendedor.objects.filter(
                        vendedor=perfil_vend,
                        proveedor_id=OuterRef("proveedor_id"),
                        marca_id=OuterRef("marca_id"),
                    )
                )
            )
        return qs

    # Nuevo: filtrar proveedores/marcas según asignaciones del usuario
    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "proveedor":
            perfil_prov = self._get_perfil_proveedor_obj(request)
            if perfil_prov:
                kwargs["queryset"] = Proveedor.objects.filter(id=perfil_prov.proveedor.id)
            else:
                perfil_vend = self._get_perfil_vendedor_obj(request)
                if perfil_vend:
                    kwargs["queryset"] = Proveedor.objects.filter(
                        asignaciones__vendedor=perfil_vend
                    ).distinct()
        elif db_field.name == "marca":
            perfil_prov = self._get_perfil_proveedor_obj(request)
            if perfil_prov:
                kwargs["queryset"] = Marca.objects.filter(
                    asignaciones__proveedor=perfil_prov.proveedor
                ).distinct()
            else:
                perfil_vend = self._get_perfil_vendedor_obj(request)
                if perfil_vend:
                    kwargs["queryset"] = Marca.objects.filter(
                        asignaciones__vendedor=perfil_vend
                    ).distinct()
                else:
                    kwargs["queryset"] = Marca.objects.filter(
                        asignaciones__isnull=False
                    ).distinct()
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def get_urls(self):
        urls = super().get_urls()
        custom = [
        ]
        return custom + urls

    def change_view(self, request, object_id, form_url='', extra_context=None):
        """Agregar datos de marcas al contexto del template"""
        extra_context = extra_context or {}
        
        # Generar datos de marcas para JavaScript
        marcas_data = {}
        asignaciones = AsignacionMarcaVendedor.objects.select_related('proveedor', 'marca').all()
        
        for asignacion in asignaciones:
            proveedor_id = str(asignacion.proveedor.id)
            if proveedor_id not in marcas_data:
                marcas_data[proveedor_id] = []
            
            marca_data = {
                'id': asignacion.marca.id,
                'nombre': asignacion.marca.nombre
            }
            if marca_data not in marcas_data[proveedor_id]:
                marcas_data[proveedor_id].append(marca_data)
        
        extra_context['marcas_data_json'] = json.dumps(marcas_data)
        return super().change_view(request, object_id, form_url, extra_context)

    def add_view(self, request, form_url='', extra_context=None):
        """Agregar datos de marcas al contexto del template"""
        extra_context = extra_context or {}
        
        # Generar datos de marcas para JavaScript
        marcas_data = {}
        asignaciones = AsignacionMarcaVendedor.objects.select_related('proveedor', 'marca').all()
        
        for asignacion in asignaciones:
            proveedor_id = str(asignacion.proveedor.id)
            if proveedor_id not in marcas_data:
                marcas_data[proveedor_id] = []
            
            marca_data = {
                'id': asignacion.marca.id,
                'nombre': asignacion.marca.nombre
            }
            if marca_data not in marcas_data[proveedor_id]:
                marcas_data[proveedor_id].append(marca_data)
        
        extra_context['marcas_data_json'] = json.dumps(marcas_data)
        return super().add_view(request, form_url, extra_context)

    # Nuevo: proteger acceso directo a objetos fuera de las asignaciones
    def has_view_permission(self, request, obj=None):
        base = super().has_view_permission(request, obj=obj)
        if not base:
            return False
        if obj is None:
            return True
        perfil_prov = self._get_perfil_proveedor_obj(request)
        if perfil_prov:
            return obj.proveedor_id == getattr(perfil_prov.proveedor, "id", None)
        perfil_vend = self._get_perfil_vendedor_obj(request)
        if perfil_vend:
            return AsignacionMarcaVendedor.objects.filter(
                vendedor=perfil_vend,
                proveedor_id=obj.proveedor_id,
                marca_id=obj.marca_id,
            ).exists()
        return True


# ─────────────────────────────────────────────────────────────────────
# Admin Línea con TARJETAS KPI + filtros + permisos por rol/proveedor
# ─────────────────────────────────────────────────────────────────────
@admin.register(SugeridoLinea)
class SugeridoLineaAdmin(admin.ModelAdmin):
    change_list_template = f"admin/{SugeridoLinea._meta.app_label}/sugeridolinea/change_list.html"

    list_display = (
        "proveedor", "marca", "nombre_almacen", "codigo_articulo", "get_descripcion_corta",
        "stock_actual", "sugerido_calculado", "sugerido_interno",
        "nuevo_sugerido_prov", "descuento_prov_pct", "descuento_prov_pct_2", "descuento_prov_pct_3",
        "presupuesto_proveedor", "costo_linea", "clasificacion", "estado_linea",
    )
    list_display_links = ("codigo_articulo",)
    list_editable = ("sugerido_interno",)
    ordering = ("-lote__fecha_extraccion", "proveedor", "marca", "codigo_articulo")

    list_filter = (
        NombreAlmacenEnLoteFilter,
        ("proveedor", admin.RelatedOnlyFieldListFilter),
        MarcaEnLoteFilter,
        FamiliaEnLoteFilter,
        SubfamiliaEnLoteFilter,
        ClasificacionEnLoteFilter,
        EstadoLineaEnLoteFilter,
    )
    search_fields = ("codigo_articulo", "referencia")

    readonly_fields_base = (
        "nombre_almacen", "proveedor", "marca",
        "referencia", "descripcion",
        "departamento", "seccion", "familia", "subfamilia",
        "stock_actual", "stock_minimo", "stock_maximo",
        "uds_compra_base", "uds_compra_mult", "embalaje",
        "ultimo_costo", "sugerido_base", "factor_almacen",
        "sugerido_calculado", "cajas_calculadas", "costo_linea",
        "clasificacion",
        "estado_linea",
        "nuevo_sugerido_prov", "descuento_prov_pct", "descuento_prov_pct_2", "descuento_prov_pct_3", "continuidad_activo",
        "nuevo_nombre_prov", "observaciones_prov", "presupuesto_proveedor",
    )

    fieldsets = (
        ("Identificación", {
            "fields": (
                ("lote", "estado_linea"),
                ("cod_almacen", "nombre_almacen"),
                ("proveedor", "marca"),
                ("codigo_articulo", "referencia"),
                ("descripcion",),
                ("departamento", "seccion", "familia", "subfamilia"),
                ("tipo", "clasificacion"),
            )
        }),
        ("Parámetros", {
            "fields": (
                ("stock_actual", "stock_minimo", "stock_maximo"),
                ("uds_compra_base", "uds_compra_mult", "embalaje"),
                ("ultimo_costo",),
                ("sugerido_base", "factor_almacen"),
                ("sugerido_calculado", "cajas_calculadas", "costo_linea"),
            )
        }),
        ("Edición interna (Compras)", {
            "fields": ("sugerido_interno", "ultima_cantidad_pedida")
        }),
        ("Respuesta del proveedor", {"fields": ("continuidad_activo", "nuevo_sugerido_prov", "descuento_prov_pct", "descuento_prov_pct_2", "descuento_prov_pct_3", "nuevo_nombre_prov", "observaciones_prov", "presupuesto_proveedor")}),
        ("Validaciones", {
            "fields": ("warning_no_multiplo", "warning_incremento_100")
        })
    )

    actions = [
        "accion_set_interno_igual_calculado",
        "accion_exportar_csv",
        "accion_exportar_xlsx",
        "accion_proveedor_enviar_respuesta",
    ]

    # ==================== Helpers de rol y debug ====================
    def _dbg(self, *args):
        print("[SugeridoLineaAdmin]", *args)

    def has_module_permission(self, request):
        return not self._es_proveedor(request) and super().has_module_permission(request)

    def has_add_permission(self, request):
        return not self._es_proveedor(request) and super().has_add_permission(request)

    def _get_perfil_proveedor_obj(self, request):
        perfil = getattr(request.user, "perfil_proveedor", None)
        try:
            if hasattr(perfil, "all"):
                return perfil.all().first()
            if hasattr(perfil, "exists") and hasattr(perfil, "model"):
                return perfil.first()
            return perfil
        except Exception:
            return None

    def _get_perfil_vendedor_obj(self, request):
        perfil = getattr(request.user, "perfil_vendedor", None)
        try:
            if hasattr(perfil, "all"):
                return perfil.all().first()
            if hasattr(perfil, "exists") and hasattr(perfil, "model"):
                return perfil.first()
            return perfil
        except Exception:
            return None

    def _es_interno(self, request) -> bool:
        return request.user.groups.filter(name='perfil_interno').exists()

    def _es_proveedor(self, request) -> bool:
        if self._es_interno(request):
            return False
        en_grupo = request.user.groups.filter(name='perfil_proveedor').exists()
        tiene_perfil = self._get_perfil_proveedor_obj(request) is not None
        return en_grupo or tiene_perfil

    # ==================== List / filtros dinámicos ====================
    def get_list_display(self, request):
        if self._es_proveedor(request):
            return (
                "marca", "nombre_almacen", "codigo_articulo", "get_descripcion_corta", "stock_actual",
                "sugerido_calculado", "nuevo_sugerido_prov", "descuento_prov_pct", "descuento_prov_pct_2", "descuento_prov_pct_3",
                "presupuesto_proveedor", "costo_linea", "clasificacion", "estado_linea"
            )
        return super().get_list_display(request)

    def get_list_display_links(self, request, list_display):
        if self._es_proveedor(request):
            return ("codigo_articulo",)
        return super().get_list_display_links(request, list_display)

    def cajas_calculadas(self, obj):
        return obj.cajas_calculadas
    cajas_calculadas.short_description = "Cajas Calc."
    cajas_calculadas.admin_order_field = "cajas_calculadas"

    def get_list_filter(self, request):
        base = list(super().get_list_filter(request))
        if self._es_proveedor(request):
            base = [
                f for f in base
                if not (f == "proveedor" or (isinstance(f, tuple) and len(f) > 0 and f[0] == "proveedor"))
            ]
        return base

    # ==================== Queryset por lote ====================
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        lote_id = request.GET.get("lote__id__exact")
        if lote_id:
            qs = qs.filter(lote_id=lote_id)
        return qs

    # ==================== URLs extra ====================
    def get_urls(self):
        urls = super().get_urls()
        custom = [
            path('<int:lote_id>/', self.admin_site.admin_view(self.changelist_por_lote), name='sugeridolinea_por_lote'),
            path('confirmar-lote-proveedor/<int:lote_id>/', self.admin_site.admin_view(self.confirmar_lote_proveedor), name='confirmar_lote_proveedor'),
            path('confirmar-pedido-icg/<int:lote_id>/', self.admin_site.admin_view(self.confirmar_pedido_icg), name='confirmar_pedido_icg'),
            path('importar-a-icg/<int:lote_id>/', self.admin_site.admin_view(self.importar_a_icg), name='importar_a_icg'),
        ]
        return custom + urls

    def changelist_por_lote(self, request, lote_id: int):
        q = request.GET.copy()
        q['lote__id__exact'] = str(lote_id)
        request.GET = q
        request.META['QUERY_STRING'] = q.urlencode()
        return self.changelist_view(request)

    # ==================== Acciones ====================
    def confirmar_lote_proveedor(self, request, lote_id):
        lote = get_object_or_404(SugeridoLote, pk=lote_id)
        perfil = self._get_perfil_proveedor_obj(request)
        if not perfil:
            self.message_user(request, 'Solo un usuario proveedor puede confirmar el sugerido.', level=messages.ERROR)
            return redirect('..')
        if lote.estado in {SugeridoLote.Estado.CONFIRMADO, SugeridoLote.Estado.COMPLETADO}:
            self.message_user(request, 'El lote ya fue confirmado/completado.', level=messages.INFO)
            return redirect(request.META.get('HTTP_REFERER', '..'))
        if not lote.lineas.filter(proveedor=perfil.proveedor).exists():
            self.message_user(request, 'No hay líneas de su proveedor en este lote.', level=messages.WARNING)
            return redirect(request.META.get('HTTP_REFERER', '..'))

        with transaction.atomic():
            lineas_qs = lote.lineas.filter(proveedor=perfil.proveedor)
            actualizadas = lineas_qs.update(sugerido_interno=Coalesce(F('nuevo_sugerido_prov'), Decimal('0')))
            lote.estado = SugeridoLote.Estado.CONFIRMADO
            lote.save(update_fields=['estado'])

        self.message_user(request, f'Lote {lote.id} confirmado correctamente. {actualizadas} línea(s) actualizada(s).', level=messages.SUCCESS)
        return redirect(request.META.get('HTTP_REFERER', '..'))

    def confirmar_pedido_icg(self, request, lote_id):
        lote = get_object_or_404(SugeridoLote, pk=lote_id)
        back = request.META.get('HTTP_REFERER', '..')
        if not self._es_interno(request):
            self.message_user(request, 'Acción solo para usuarios internos.', level=messages.ERROR)
            return redirect(back)
        if lote.estado == SugeridoLote.Estado.COMPLETADO:
            self.message_user(request, 'El lote ya está completado.', level=messages.INFO)
            return redirect(back)
        lote.estado = SugeridoLote.Estado.COMPLETADO
        lote.save(update_fields=['estado'])
        self.message_user(request, f'Lote {lote.id} marcado como COMPLETADO (informativo).', level=messages.SUCCESS)
        return redirect(back)

    def importar_a_icg(self, request, lote_id):
        lote = get_object_or_404(SugeridoLote, pk=lote_id)
        back = request.META.get('HTTP_REFERER', '..')

        if not self._es_interno(request):
            self.message_user(request, 'Acción solo para usuarios internos.', level=messages.ERROR)
            return redirect(back)

        try:
            kwargs = {}
            if getattr(lote, "numserie", None):
                kwargs["numserie"] = lote.numserie
            if getattr(lote, "subserie", None):
                kwargs["subserie_n"] = lote.subserie

            pedidos = crear_pedido_compra_desde_lote(lote_id=lote.id, **kwargs)
            if pedidos:
                resumen = ", ".join([f"{p.get('numserie')}-{p.get('numpedido')}({p.get('cod_almacen')})" for p in pedidos])
                self.message_user(request, f"{len(pedidos)} pedido(s) en ICG generados: {resumen}.", level=messages.SUCCESS)
            else:
                self.message_user(request, "No se generaron pedidos (sin líneas válidas).", level=messages.INFO)
        except Exception as e:
            self.message_user(request, f'Error al generar pedido en ICG: {e}', level=messages.ERROR)
        return redirect(back)

    def accion_exportar_xlsx(self, request, qs):
        xlsx_bytes, filename = export_lines_to_xlsx(qs)
        resp = HttpResponse(
            xlsx_bytes,
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        resp["Content-Disposition"] = f'attachment; filename="{filename}"'
        return resp

    @admin.action(description="Enviar respuesta (proveedor)")
    def accion_proveedor_enviar_respuesta(self, request, qs):
        perfil_prov = self._get_perfil_proveedor_obj(request)
        if not perfil_prov:
            self.message_user(request, "Acción solo para proveedores.", messages.ERROR)
            return

        lineas_validas = qs.filter(proveedor=perfil_prov.proveedor)
        if not lineas_validas.exists():
            self.message_user(request, "No hay líneas válidas para su proveedor.", messages.WARNING)
            return

        count = lineas_validas.update(estado_linea="RESPONDIDA")
        try:
            notificar_compras_respuesta_proveedor(perfil_prov.proveedor, lineas_validas.first().lote)
        except Exception as e:
            self.message_user(request, f"Líneas actualizadas pero error en notificación: {e}", messages.WARNING)
            return

        self.message_user(request, f"{count} líneas marcadas como respondidas y notificación enviada.", messages.SUCCESS)

    # ==================== Vista principal ====================
    def changelist_view(self, request, extra_context=None):
        es_proveedor = self._es_proveedor(request)
        original_editable = self.list_editable
        puede_editar_clasificacion_c = request.user.groups.filter(name='clasificacion_c').exists()
        es_interno = self._es_interno(request)
        if es_interno:
            es_proveedor = False

        if request.method == 'POST':
            ids = set()
            for k in request.POST.keys():
                if k.startswith('linea_id_'):
                    try:
                        ids.add(int(k.split('_')[-1]))
                    except:
                        pass
                elif k.startswith((
                    'sugerido_interno_',
                    'nuevo_sugerido_prov_',
                    'descuento_prov_pct_',
                    'descuento_prov_pct_2_',
                    'descuento_prov_pct_3_',
                    'continuidad_activo_',
                    'nuevo_nombre_prov_',
                    'observaciones_prov_',
                    'clasificacion_',
                )):
                    try:
                        ids.add(int(k.split('_')[-1]))
                    except:
                        pass

            self._dbg("POST ids detectados:", sorted(list(ids))[:10], "... total:", len(ids))

            lineas = self.model.objects.filter(pk__in=ids).select_related('lote')
            actualizados = 0

            def _dec(v):
                if v in (None, '', 'None'):
                    return None
                try:
                    return Decimal(str(v).replace(',', '.'))
                except Exception:
                    return None

            with transaction.atomic():
                for ln in lineas:
                    cambio = False
                    changed_fields = []
                    cla = (ln.clasificacion or '').strip().upper()
                    estado_lote = (getattr(ln.lote, 'estado', '') or '').strip().upper()
                    estado_linea = (ln.estado_linea or '').strip().upper()
                    pid = ln.pk

                    self._dbg(f"Procesando línea {pid} (cla={cla}, estado_lote={estado_lote}, estado_linea={estado_linea})")

                    if es_proveedor:
                        perfil = self._get_perfil_proveedor_obj(request)
                        en_grupo = request.user.groups.filter(name='perfil_proveedor').exists()
                        self._dbg(f"  Tiene objeto perfil? {bool(perfil)}; En grupo perfil_proveedor? {en_grupo}")

                        # ===== CAMBIO: validación de proveedor =====
                        if perfil and hasattr(perfil, 'proveedor'):
                            if perfil.proveedor != ln.proveedor:
                                self._dbg("  -> Skip: perfil existe pero proveedor NO coincide con la línea.")
                                continue
                        else:
                            # No hay perfil con proveedor; solo grupo => no bloqueamos por coincidencia
                            self._dbg("  -> Sin objeto perfil con proveedor; permitimos edición por pertenecer al grupo.")

                        # Estados que bloquean
                        if cla == 'I' or estado_lote in {'CONFIRMADO', 'COMPLETADO'} or estado_linea == 'ORDENADA':
                            self._dbg("  -> Skip por estado/clasificación.")
                            continue

                        # === Inputs crudos
                        m_d1  = request.POST.get(f'descuento_prov_pct_{pid}')
                        m_d2  = request.POST.get(f'descuento_prov_pct_2_{pid}')
                        m_d3  = request.POST.get(f'descuento_prov_pct_3_{pid}')
                        m_cont = request.POST.get(f'continuidad_activo_{pid}')
                        m_nom  = request.POST.get(f'nuevo_nombre_prov_{pid}')
                        m_obs  = request.POST.get(f'observaciones_prov_{pid}')
                        m_nsug = request.POST.get(f'nuevo_sugerido_prov_{pid}')

                        self._dbg(f"  Inputs crudos: d1='{m_d1}' d2='{m_d2}' d3='{m_d3}' cont='{m_cont}' nom='{m_nom}' obs='{m_obs}' nsug='{m_nsug}'")

                        # === Parseos
                        v_d1 = _dec(m_d1)
                        v_d2 = _dec(m_d2)
                        v_d3 = _dec(m_d3)
                        v_nsug = _dec(m_nsug)
                        v_cont = (m_cont is not None)

                        self._dbg(f"  Parseos: d1={v_d1} d2={v_d2} d3={v_d3} nsug={v_nsug} cont={v_cont}")
                        self._dbg(f"  Valores actuales: d1={ln.descuento_prov_pct} d2={ln.descuento_prov_pct_2} d3={ln.descuento_prov_pct_3} nsug={ln.nuevo_sugerido_prov} cont={ln.continuidad_activo} nom='{ln.nuevo_nombre_prov}' obs='{ln.observaciones_prov}'")

                        # === CABECERA (si vienen y cambian)
                        if v_d1 is not None and v_d1 != ln.descuento_prov_pct:
                            ln.descuento_prov_pct = v_d1; cambio = True; changed_fields.append('descuento_prov_pct')
                        if v_d2 is not None and v_d2 != ln.descuento_prov_pct_2:
                            ln.descuento_prov_pct_2 = v_d2; cambio = True; changed_fields.append('descuento_prov_pct_2')
                        if v_d3 is not None and v_d3 != ln.descuento_prov_pct_3:
                            ln.descuento_prov_pct_3 = v_d3; cambio = True; changed_fields.append('descuento_prov_pct_3')

                        if (f'continuidad_activo_{pid}' in request.POST) and (v_cont != ln.continuidad_activo):
                            ln.continuidad_activo = v_cont; cambio = True; changed_fields.append('continuidad_activo')

                        if (m_nom is not None) and (m_nom != ln.nuevo_nombre_prov):
                            ln.nuevo_nombre_prov = m_nom; cambio = True; changed_fields.append('nuevo_nombre_prov')

                        if (m_obs is not None) and (m_obs != ln.observaciones_prov):
                            ln.observaciones_prov = m_obs; cambio = True; changed_fields.append('observaciones_prov')

                        # Propagar descuentos a hermanos (mismo artículo en el lote)
                        if any(x is not None for x in [v_d1, v_d2, v_d3]):
                            self._dbg("  Propagando descuentos a hermanos del mismo código...")
                            hermanos = self.model.objects.filter(
                                lote_id=ln.lote_id,
                                codigo_articulo=ln.codigo_articulo
                            ).exclude(pk=ln.pk)
                            for h in hermanos:
                                h_cambio = False
                                if v_d1 is not None and h.descuento_prov_pct != v_d1:
                                    h.descuento_prov_pct = v_d1; h_cambio = True
                                if v_d2 is not None and h.descuento_prov_pct_2 != v_d2:
                                    h.descuento_prov_pct_2 = v_d2; h_cambio = True
                                if v_d3 is not None and h.descuento_prov_pct_3 != v_d3:
                                    h.descuento_prov_pct_3 = v_d3; h_cambio = True
                                if h_cambio:
                                    h.save(update_fields=['descuento_prov_pct', 'descuento_prov_pct_2', 'descuento_prov_pct_3'])
                                    actualizados += 1
                            self._dbg("  Propagación terminada.")

                        # POR LÍNEA: sugerido_prov solo A/B
                        proveedor_puede_editar = (cla in {'A', 'B'})
                        self._dbg(f"  Puede editar 'nuevo_sugerido_prov' (A/B)? {proveedor_puede_editar}")
                        if proveedor_puede_editar and (m_nsug is not None):
                            if v_nsug is not None and v_nsug != ln.nuevo_sugerido_prov:
                                ln.nuevo_sugerido_prov = v_nsug; cambio = True; changed_fields.append('nuevo_sugerido_prov')
                            else:
                                self._dbg("  nsug sin cambio o no parseable (None).")

                    else:
                        if not es_interno:
                            continue
                        if cla == 'I' or estado_linea == 'ORDENADA' or estado_lote in {'CONFIRMADO', 'COMPLETADO'}:
                            continue

                        def _dec_local(v):
                            if v in (None, '', 'None'):
                                return None
                            try:
                                return Decimal(str(v).replace(',', '.'))
                            except Exception:
                                return None

                        editable_interno = not (cla == 'C' and not puede_editar_clasificacion_c)

                        m_si = request.POST.get(f'sugerido_interno_{pid}')
                        v_si = _dec_local(m_si)
                        if v_si is not None and editable_interno and v_si != ln.sugerido_interno:
                            ln.sugerido_interno = v_si; cambio = True; changed_fields.append('sugerido_interno')

                        m_clas = request.POST.get(f'clasificacion_{pid}')
                        if m_clas is not None:
                            v_clas = (m_clas or '').strip().upper()
                            if v_clas != (ln.clasificacion or '').strip().upper():
                                ln.clasificacion = v_clas; cambio = True; changed_fields.append('clasificacion')

                    if cambio:
                        self._dbg(f"  Cambios en {pid}: {changed_fields}")
                        ln.save(update_fields=list(set(changed_fields)))
                        actualizados += 1
                    else:
                        self._dbg(f"  Sin cambios aplicables en {pid}.")

            if actualizados:
                self.message_user(request, f"{actualizados} línea(s) actualizada(s).", level=messages.SUCCESS)
            else:
                self.message_user(request, "No hubo cambios aplicables.", level=messages.INFO)
            return redirect(request.get_full_path())

        try:
            response = super().changelist_view(request, extra_context=extra_context)
            try:
                cl = response.context_data["cl"]
                qs = cl.queryset
            except Exception:
                return response

            if request.GET.get("lote__id__exact"):
                try:
                    cl.full_result_count = cl.result_count
                except Exception:
                    pass

            qty_expr = Case(
                When(sugerido_interno__gt=0, then=F("sugerido_interno")),
                default=F("sugerido_calculado"),
                output_field=DecimalField(max_digits=16, decimal_places=2),
            )
            kpis = qs.aggregate(
                costo_total=Coalesce(Sum("costo_linea"), Decimal("0")),
                total_unidades=Coalesce(Sum(qty_expr), Decimal("0")),
                total_cajas=Coalesce(Sum("cajas_calculadas"), Decimal("0")),
                total_articulos=Count("referencia", distinct=True),
                articulos_con_pedido=Count(Case(When(Q(sugerido_interno__gt=0) | Q(sugerido_calculado__gt=0), then=1))),
                costo_sugerido_prov=Coalesce(Sum(F("nuevo_sugerido_prov") * F("ultimo_costo")), Decimal("0")),
                costo_sugerido_interno=Coalesce(Sum(F("sugerido_interno") * F("ultimo_costo")), Decimal("0")),
            )

            presupuesto_total = Decimal("0")
            lote_id = request.GET.get('lote__id__exact')
            if lote_id:
                try:
                    lote_obj = SugeridoLote.objects.select_related('proveedor').get(pk=lote_id)
                    if lote_obj.proveedor and lote_obj.proveedor.presupuesto_mensual:
                        presupuesto_total = lote_obj.proveedor.presupuesto_mensual
                except SugeridoLote.DoesNotExist:
                    pass
            kpis["presupuesto_total"] = presupuesto_total
            kpis["costo_promedio_por_articulo"] = (kpis["costo_total"] / kpis["articulos_con_pedido"] if kpis["articulos_con_pedido"] else Decimal("0"))
            kpis["gap_interno_vs_calc"] = kpis["costo_sugerido_interno"] - kpis["costo_total"]
            kpis["gap_prov_vs_calc"] = kpis["costo_sugerido_prov"] - kpis["costo_total"]

            cumplimiento_presupuesto_pct = Decimal("0")
            if lote_id:
                try:
                    lote_obj = SugeridoLote.objects.select_related('proveedor').get(pk=lote_id)
                    if lote_obj.proveedor:
                        ahora = timezone.now()
                        inicio_mes = ahora.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
                        total_sugeridos_mes = SugeridoLinea.objects.filter(
                            proveedor=lote_obj.proveedor,
                            lote__fecha_extraccion__gte=inicio_mes,
                            lote__fecha_extraccion__lt=ahora
                        ).aggregate(
                            total=Coalesce(Sum("costo_linea"), Decimal("0"))
                        )["total"]
                        if lote_obj.proveedor.presupuesto_mensual and lote_obj.proveedor.presupuesto_mensual > 0:
                            cumplimiento_presupuesto_pct = (total_sugeridos_mes / lote_obj.proveedor.presupuesto_mensual) * 100
                except SugeridoLote.DoesNotExist:
                    pass

            kpis["cumplimiento_presupuesto_pct"] = cumplimiento_presupuesto_pct
            kpis["lineas_con_algún_descuento_pct"] = (qs.filter(Q(descuento_prov_pct__gt=0) | Q(descuento_prov_pct_2__gt=0) | Q(descuento_prov_pct_3__gt=0)).count() / (kpis["total_articulos"] or 1)) * 100
            response.context_data["kpis"] = kpis

            articulos_pivot = {}
            almacenes_set = set()
            for ln in qs:
                key = ln.codigo_articulo
                if key not in articulos_pivot:
                    articulos_pivot[key] = {}
                articulos_pivot[key][ln.nombre_almacen] = ln
                almacenes_set.add(ln.nombre_almacen)

            orden_almacenes = [
                "MERCASUR CALDAS",
                "MERCASUR CENTRO",
                "MERCASUR CABECERA",
                "MERCASUR SOTOMAYOR"
            ]
            almacenes_list = sorted(
                almacenes_set,
                key=lambda x: orden_almacenes.index(x) if x in orden_almacenes else 99
            )
            response.context_data["articulos_pivot"] = articulos_pivot
            response.context_data["almacenes_list"] = almacenes_list

            lote_id = request.GET.get('lote__id__exact')
            if not lote_id:
                ids = list(qs.values_list('lote_id', flat=True).distinct())
                if len(ids) == 1:
                    lote_id = ids[0]
            response.context_data['lote_id_actual'] = lote_id
            response.context_data['es_proveedor'] = es_proveedor
            response.context_data['es_interno'] = es_interno
            response.context_data['puede_editar_clasificacion_c'] = puede_editar_clasificacion_c

            lote_estado = None
            inputs_disabled = False
            if lote_id:
                try:
                    lote_obj = SugeridoLote.objects.only('estado').get(pk=lote_id)
                    lote_estado = lote_obj.estado
                    inputs_disabled = (str(lote_estado).upper() == 'COMPLETADO')
                    es_vendedor_grupo = request.user.groups.filter(name='perfil_vendedor').exists()
                    if es_vendedor_grupo and str(lote_estado).upper() in {'CONFIRMADO', 'COMPLETADO'}:
                        inputs_disabled = True
                    response.context_data['ocultar_boton_confirmar_proveedor'] = str(lote_estado).upper() in {'CONFIRMADO', 'COMPLETADO'}
                except SugeridoLote.DoesNotExist:
                    response.context_data['ocultar_boton_confirmar_proveedor'] = False

            response.context_data['lote_estado'] = lote_estado
            response.context_data['inputs_disabled'] = inputs_disabled

            return response
        finally:
            self.list_editable = original_editable

    def get_descripcion_corta(self, obj):
        txt = getattr(obj, 'descripcion', '') or ''
        return txt if len(txt) <= 50 else txt[:47] + '…'
    get_descripcion_corta.short_description = "Descripción"