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
from django.core.exceptions import ValidationError
from decimal import Decimal
from datetime import datetime
import csv
import json
from django.template.loader import render_to_string
from ..filters import (
    MarcaEnLoteFilter,
    NombreAlmacenEnLoteFilter,
    FamiliaEnLoteFilter,
    SubfamiliaEnLoteFilter,
    ClasificacionEnLoteFilter,
    EstadoLineaEnLoteFilter
)

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
from ..services.kpi_utils import obtener_kpis_por_lote
from ..services.icg_import import actualizar_kpis_lote
from datetime import timedelta
from ..forms import SugeridoLoteAdminForm

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
    fields = ("nombre", "proveedor", "marcas", "observaciones")  # Orden específico: proveedor primero, luego marcas
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
            # Filtrar lotes que tengan al menos una marca asignada al vendedor
            return qs.filter(
                marcas__in=Marca.objects.filter(
                    asignaciones__vendedor=perfil_vend
                )
            ).distinct()
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
        return super().formfield_for_foreignkey(db_field, request, **kwargs)
    
    def formfield_for_manytomany(self, db_field, request, **kwargs):
        if db_field.name == "marcas":
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
        return super().formfield_for_manytomany(db_field, request, **kwargs)

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
        base = super().has_view_permission(request, obj)
        if not base:
            return False
        if obj is None:
            return True
        perfil_prov = self._get_perfil_proveedor_obj(request)
        if perfil_prov:
            return obj.proveedor_id == getattr(perfil_prov.proveedor, "id", None)
        perfil_vend = self._get_perfil_vendedor_obj(request)
        if perfil_vend:
            # Verificar si al menos una de las marcas del lote está asignada al vendedor
            marcas_lote = obj.marcas.all()
            if not marcas_lote.exists():
                return True  # Si no hay marcas, permitir ver
            return AsignacionMarcaVendedor.objects.filter(
                vendedor=perfil_vend,
                proveedor_id=obj.proveedor_id,
                marca__in=marcas_lote,
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
    ordering = ("descripcion",)  # Ordenar por descripción A-Z

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
        return False  # Ocultar completamente del menú de módulos

    def has_add_permission(self, request):
        return False  # Desabilitar completamente el botón de añadir

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
        """Confirmar el lote desde la perspectiva del proveedor"""
        lote = get_object_or_404(SugeridoLote, pk=lote_id)
        
        # Debug: verificar permisos del usuario
        es_proveedor = self._es_proveedor(request)
        perfil = self._get_perfil_proveedor_obj(request)
        en_grupo = request.user.groups.filter(name='perfil_proveedor').exists()
        
        print(f"[DEBUG confirmar_lote_proveedor]")
        print(f"  Usuario: {request.user.username}")
        print(f"  Es proveedor (método): {es_proveedor}")
        print(f"  Perfil objeto: {perfil}")
        print(f"  En grupo 'perfil_proveedor': {en_grupo}")
        print(f"  Grupos del usuario: {list(request.user.groups.values_list('name', flat=True))}")
        
        # Validación: debe estar en el grupo O tener perfil
        if not es_proveedor and not en_grupo:
            messages.error(
                request, 
                f'Solo un usuario proveedor puede confirmar el sugerido. '
                f'Usuario: {request.user.username}, Grupos: {", ".join(request.user.groups.values_list("name", flat=True))}'
            )
            return redirect('admin:Compras_sugeridolote_changelist')
        
        # Obtener el proveedor del lote
        proveedor_lote = lote.proveedor
        
        if not proveedor_lote:
            messages.error(request, 'Este lote no tiene un proveedor asignado.')
            return redirect('admin:sugeridolinea_por_lote', lote_id)
        
        # Determinar el proveedor a usar para la confirmación
        proveedor_validado = None
        
        # Caso 1: Usuario tiene perfil de proveedor
        if perfil and hasattr(perfil, 'proveedor') and perfil.proveedor:
            if perfil.proveedor.id != proveedor_lote.id:
                messages.error(
                    request, 
                    f'Este lote pertenece a otro proveedor. '
                    f'Su proveedor: {perfil.proveedor.nombre}, Lote: {proveedor_lote.nombre}'
                )
                return redirect('admin:sugeridolinea_por_lote', lote_id)
            proveedor_validado = perfil.proveedor
            print(f"  -> Usando proveedor del perfil: {proveedor_validado.nombre}")
        
        # Caso 2: Usuario en grupo pero sin perfil - usar proveedor del lote
        elif en_grupo:
            proveedor_validado = proveedor_lote
            print(f"  -> Usuario en grupo sin perfil, usando proveedor del lote: {proveedor_validado.nombre}")
        
        # Caso 3: No se puede determinar el proveedor
        else:
            messages.error(
                request, 
                'No se pudo determinar el proveedor. Contacte al administrador para que le asigne un perfil de proveedor.'
            )
            return redirect('admin:sugeridolinea_por_lote', lote_id)
        
        # Validar estado del lote
        if lote.estado in {SugeridoLote.Estado.CONFIRMADO, SugeridoLote.Estado.COMPLETADO}:
            messages.info(request, f'El lote ya fue {lote.estado.lower()}.')
            return redirect('admin:sugeridolinea_por_lote', lote_id)
        
        # Validar que existan líneas del proveedor
        lineas_count = lote.lineas.filter(proveedor=proveedor_validado).count()
        if lineas_count == 0:
            messages.warning(
                request, 
                f'No hay líneas del proveedor {proveedor_validado.nombre} en este lote.'
            )
            return redirect('admin:sugeridolinea_por_lote', lote_id)

        print(f"  -> Confirmando {lineas_count} líneas del proveedor {proveedor_validado.nombre}")

        # Actualizar líneas y estado
        try:
            with transaction.atomic():
                lineas_qs = lote.lineas.filter(proveedor=proveedor_validado)
                
                # Copiar nuevo_sugerido_prov a sugerido_interno
                actualizadas = lineas_qs.update(
                    sugerido_interno=Coalesce(F('nuevo_sugerido_prov'), Decimal('0'))
                )
                
                print(f"  -> {actualizadas} líneas actualizadas")
                
                # Cambiar estado del lote
                lote.estado = SugeridoLote.Estado.CONFIRMADO
                lote.save(update_fields=['estado'])
                
                print(f"  -> Estado del lote cambiado a CONFIRMADO")
                
                # Recalcular totales si el método existe
                if hasattr(lote, 'recalcular_totales'):
                    try:
                        lote.recalcular_totales()
                        print(f"  -> Totales recalculados")
                    except Exception as e:
                        print(f"  -> Advertencia al recalcular totales: {e}")
                else:
                    print(f"  -> El modelo SugeridoLote no tiene método recalcular_totales")
                
            messages.success(
                request, 
                f'✅ Lote {lote.id} confirmado correctamente por {proveedor_validado.nombre}. '
                f'{actualizadas} línea(s) actualizada(s).'
            )
            print(f"  -> Confirmación completada exitosamente")
            
        except Exception as e:
            print(f"  -> ERROR: {str(e)}")
            import traceback
            traceback.print_exc()
            messages.error(request, f'❌ Error al confirmar el lote: {str(e)}')
        
        # Redireccionar a la vista de líneas del lote
        return redirect('admin:sugeridolinea_por_lote', lote_id)

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
                    'ultimo_costo_',
                )):
                    try:
                        ids.add(int(k.split('_')[-1]))
                    except:
                        pass

            self._dbg("POST ids detectados:", sorted(list(ids))[:10], "... total:", len(ids))
            self._dbg("POST keys completo:", list(request.POST.keys())[:20])
            self._dbg("Usuario es_interno:", es_interno, "es_proveedor:", es_proveedor)

            lineas = self.model.objects.filter(pk__in=ids).select_related('lote')
            actualizados = 0
            errores_validacion = []

            def _dec(v):
                if v in (None, '', 'None'):
                    return None
                try:
                    # Limpiar puntos (separadores de miles) y comas antes de convertir
                    v_limpio = str(v).replace('.', '').replace(',', '.')
                    return Decimal(v_limpio)
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

                        if perfil and hasattr(perfil, 'proveedor'):
                            if perfil.proveedor != ln.proveedor:
                                self._dbg("  -> Skip: perfil existe pero proveedor NO coincide con la línea.")
                                continue
                        else:
                            self._dbg("  -> Sin objeto perfil con proveedor; permitimos edición por pertenecer al grupo")

                        # PROTECCIÓN: Proveedores NO pueden editar líneas con clasificación I o C
                        if cla in {'I', 'C'} or estado_lote in {'CONFIRMADO', 'COMPLETADO'} or estado_linea == 'ORDENADA':
                            self._dbg(f"  -> Skip por estado/clasificación (cla={cla}).")
                            continue

                        m_ucosto = request.POST.get(f'ultimo_costo_{pid}')
                        m_d1  = request.POST.get(f'descuento_prov_pct_{pid}')
                        m_d2  = request.POST.get(f'descuento_prov_pct_2_{pid}')
                        m_d3  = request.POST.get(f'descuento_prov_pct_3_{pid}')
                        m_cont = request.POST.get(f'continuidad_activo_{pid}')
                        m_nom  = request.POST.get(f'nuevo_nombre_prov_{pid}')
                        m_obs  = request.POST.get(f'observaciones_prov_{pid}')
                        m_nsug = request.POST.get(f'nuevo_sugerido_prov_{pid}')

                        self._dbg(f"  Inputs crudos: ucosto='{m_ucosto}' d1='{m_d1}' d2='{m_d2}' d3='{m_d3}' cont='{m_cont}' nom='{m_nom}' obs='{m_obs}' nsug='{m_nsug}'")

                        v_ucosto = _dec(m_ucosto)
                        v_d1 = _dec(m_d1)
                        v_d2 = _dec(m_d2)
                        v_d3 = _dec(m_d3)
                        v_nsug = _dec(m_nsug)
                        v_cont = (m_cont is not None)

                        self._dbg(f"  Parseos: ucosto={v_ucosto} d1={v_d1} d2={v_d2} d3={v_d3} nsug={v_nsug} cont={v_cont}")
                        self._dbg(f"  Valores actuales: ucosto={ln.ultimo_costo} d1={ln.descuento_prov_pct} d2={ln.descuento_prov_pct_2} d3={ln.descuento_prov_pct_3} nsug={ln.nuevo_sugerido_prov} cont={ln.continuidad_activo} nom='{ln.nuevo_nombre_prov}' obs='{ln.observaciones_prov}'")

                        # NUEVO: Procesar último costo (NO permitir edición para clasificación I)
                        if cla != 'I' and v_ucosto is not None and v_ucosto != ln.ultimo_costo:
                            ln.ultimo_costo = v_ucosto
                            cambio = True
                            changed_fields.append('ultimo_costo')
                            # Propagar a hermanos del mismo código
                            hermanos = self.model.objects.filter(
                                lote_id=ln.lote_id,
                                codigo_articulo=ln.codigo_articulo
                            ).exclude(pk=ln.pk)
                            for h in hermanos:
                                h_cla = (h.clasificacion or '').strip().upper()
                                # Solo propagar si el hermano tampoco es I
                                if h_cla != 'I' and h.ultimo_costo != v_ucosto:
                                    h.ultimo_costo = v_ucosto
                                    try:
                                        h.save(update_fields=['ultimo_costo', 'costo_linea'])
                                        actualizados += 1
                                    except ValidationError as e:
                                        errores_validacion.append(f"Línea {h.pk} ({h.codigo_articulo}): {'; '.join(e.messages)}")
                        elif cla == 'I' and m_ucosto:
                            self._dbg(f"  -> último_costo NO editable para clasificación I")

                        # PROTECCIÓN: No permitir cambios en descuentos si clasificación es I o C
                        puede_editar_descuentos = cla not in {'I', 'C'}
                        
                        if puede_editar_descuentos:
                            if v_d1 is not None and v_d1 != ln.descuento_prov_pct:
                                ln.descuento_prov_pct = v_d1; cambio = True; changed_fields.append('descuento_prov_pct')
                            if v_d2 is not None and v_d2 != ln.descuento_prov_pct_2:
                                ln.descuento_prov_pct_2 = v_d2; cambio = True; changed_fields.append('descuento_prov_pct_2')
                            if v_d3 is not None and v_d3 != ln.descuento_prov_pct_3:
                                ln.descuento_prov_pct_3 = v_d3; cambio = True; changed_fields.append('descuento_prov_pct_3')
                        else:
                            self._dbg(f"  -> Descuentos NO editables para clasificación {cla}")

                        if (f'continuidad_activo_{pid}' in request.POST) and (v_cont != ln.continuidad_activo):
                            ln.continuidad_activo = v_cont; cambio = True; changed_fields.append('continuidad_activo')

                        if (m_nom is not None) and (m_nom != ln.nuevo_nombre_prov):
                            ln.nuevo_nombre_prov = m_nom; cambio = True; changed_fields.append('nuevo_nombre_prov')

                        if (m_obs is not None) and (m_obs != ln.observaciones_prov):
                            ln.observaciones_prov = m_obs; cambio = True; changed_fields.append('observaciones_prov')

                        if puede_editar_descuentos and any(x is not None for x in [v_d1, v_d2, v_d3]):
                            self._dbg("  Propagando descuentos a hermanos del mismo código...")
                            hermanos = self.model.objects.filter(
                                lote_id=ln.lote_id,
                                codigo_articulo=ln.codigo_articulo
                            ).exclude(pk=ln.pk)
                            for h in hermanos:
                                h_cla = (h.clasificacion or '').strip().upper()
                                # Solo propagar si el hermano tampoco es I o C
                                if h_cla not in {'I', 'C'}:
                                    h_cambio = False
                                    if v_d1 is not None and h.descuento_prov_pct != v_d1:
                                        h.descuento_prov_pct = v_d1; h_cambio = True
                                    if v_d2 is not None and h.descuento_prov_pct_2 != v_d2:
                                        h.descuento_prov_pct_2 = v_d2; h_cambio = True
                                    if v_d3 is not None and h.descuento_prov_pct_3 != v_d3:
                                        h.descuento_prov_pct_3 = v_d3; h_cambio = True
                                    if h_cambio:
                                        try:
                                            h.save(update_fields=['descuento_prov_pct', 'descuento_prov_pct_2', 'descuento_prov_pct_3'])
                                            actualizados += 1
                                        except ValidationError as e:
                                            errores_validacion.append(f"Línea {h.pk} ({h.codigo_articulo}): {'; '.join(e.messages)}")
                                            self._dbg(f"  Error validación en hermano {h.pk}: {e}")
                            self._dbg("  Propagación terminada.")

                        proveedor_puede_editar = (cla in {'A', 'B', 'D'})
                        self._dbg(f"  Puede editar 'nuevo_sugerido_prov' (A/B/D)? {proveedor_puede_editar}")
                        if proveedor_puede_editar and (m_nsug is not None):
                            if v_nsug is not None and v_nsug != ln.nuevo_sugerido_prov:
                                ln.nuevo_sugerido_prov = v_nsug; cambio = True; changed_fields.append('nuevo_sugerido_prov')
                            else:
                                self._dbg("  nsug sin cambio o no parseable (None).")

                    else:
                        # Bloque de procesamiento para usuarios INTERNOS/COMPRAS
                        self._dbg(f"  -> Entrando en bloque de USUARIOS INTERNOS (es_interno={es_interno})")
                        if not es_interno:
                            self._dbg(f"  -> Skip: usuario no es proveedor ni interno")
                            continue
                        
                        # USUARIOS INTERNOS: Pueden editar todas las clasificaciones
                        # Solo bloquear si la línea ya fue ordenada o el lote está completado
                        puede_editar_en_confirmado = estado_lote == 'CONFIRMADO'
                        
                        if estado_linea == 'ORDENADA' or estado_lote == 'COMPLETADO':
                            self._dbg(f"  -> Skip por estado_linea={estado_linea}, estado_lote={estado_lote}")
                            continue

                        def _dec_local(v):
                            if v in (None, '', 'None'):
                                return None
                            try:
                                # Limpiar puntos (separadores de miles) y comas antes de convertir
                                v_limpio = str(v).replace('.', '').replace(',', '.')
                                return Decimal(v_limpio)
                            except Exception:
                                return None

                        # PROTECCIÓN: Solo usuarios con permiso 'clasificacion_c' pueden editar clasificación C
                        editable_interno = not (cla == 'C' and not puede_editar_clasificacion_c)

                        # USUARIOS INTERNOS: Pueden editar en estado CONFIRMADO
                        # Ya no limitamos solo a sugerido_interno, permitimos editar costos y descuentos también
                        if puede_editar_en_confirmado:
                            m_si = request.POST.get(f'sugerido_interno_{pid}')
                            v_si = _dec_local(m_si)
                            
                            # USUARIOS INTERNOS: Pueden editar sugerido_interno sin restricciones de clasificación
                            if v_si is not None and editable_interno and v_si != ln.sugerido_interno:
                                ln.sugerido_interno = v_si
                                cambio = True
                                changed_fields.append('sugerido_interno')
                            
                            # Procesar también costos y descuentos en estado CONFIRMADO
                            # (no hacer continue, seguir procesando los demás campos)

                        m_ucosto = request.POST.get(f'ultimo_costo_{pid}')
                        m_d1  = request.POST.get(f'descuento_prov_pct_{pid}')
                        m_d2  = request.POST.get(f'descuento_prov_pct_2_{pid}')
                        m_d3  = request.POST.get(f'descuento_prov_pct_3_{pid}')
                        
                        self._dbg(f"  Valores POST - ucosto:'{m_ucosto}' d1:'{m_d1}' d2:'{m_d2}' d3:'{m_d3}'")
                        
                        v_ucosto = _dec_local(m_ucosto)
                        v_d1 = _dec_local(m_d1)
                        v_d2 = _dec_local(m_d2)
                        v_d3 = _dec_local(m_d3)
                        
                        self._dbg(f"  Valores parseados - ucosto:{v_ucosto} d1:{v_d1} d2:{v_d2} d3:{v_d3}")
                        self._dbg(f"  Valores actuales DB - ucosto:{ln.ultimo_costo} d1:{ln.descuento_prov_pct} d2:{ln.descuento_prov_pct_2} d3:{ln.descuento_prov_pct_3}")

                        # NUEVO: Procesar último costo para internos (usuarios internos SÍ pueden editar)
                        self._dbg(f"  Procesando ultimo_costo: cla={cla}, v_ucosto={v_ucosto}, ln.ultimo_costo={ln.ultimo_costo}")
                        if v_ucosto is not None and v_ucosto != ln.ultimo_costo:
                            self._dbg(f"  -> CAMBIANDO ultimo_costo de {ln.ultimo_costo} a {v_ucosto}")
                            ln.ultimo_costo = v_ucosto
                            cambio = True
                            changed_fields.append('ultimo_costo')
                            # Propagar a hermanos
                            hermanos = self.model.objects.filter(
                                lote_id=ln.lote_id,
                                codigo_articulo=ln.codigo_articulo
                            ).exclude(pk=ln.pk)
                            for h in hermanos:
                                if h.ultimo_costo != v_ucosto:
                                    h.ultimo_costo = v_ucosto
                                    try:
                                        h.save(update_fields=['ultimo_costo', 'costo_linea'])
                                        actualizados += 1
                                    except ValidationError as e:
                                        errores_validacion.append(f"Línea {h.pk} ({h.codigo_articulo}): {'; '.join(e.messages)}")

                        # USUARIOS INTERNOS: Pueden editar descuentos sin restricciones de clasificación
                        self._dbg(f"  Usuario interno puede editar descuentos (cla={cla})")
                        self._dbg(f"  Comparando descuentos:")
                        self._dbg(f"    d1: {v_d1} vs {ln.descuento_prov_pct} -> cambio={v_d1 is not None and v_d1 != ln.descuento_prov_pct}")
                        self._dbg(f"    d2: {v_d2} vs {ln.descuento_prov_pct_2} -> cambio={v_d2 is not None and v_d2 != ln.descuento_prov_pct_2}")
                        self._dbg(f"    d3: {v_d3} vs {ln.descuento_prov_pct_3} -> cambio={v_d3 is not None and v_d3 != ln.descuento_prov_pct_3}")
                        
                        if v_d1 is not None and v_d1 != ln.descuento_prov_pct:
                            self._dbg(f"  -> CAMBIANDO d1 de {ln.descuento_prov_pct} a {v_d1}")
                            ln.descuento_prov_pct = v_d1
                            cambio = True
                            changed_fields.append('descuento_prov_pct')
                        if v_d2 is not None and v_d2 != ln.descuento_prov_pct_2:
                            self._dbg(f"  -> CAMBIANDO d2 de {ln.descuento_prov_pct_2} a {v_d2}")
                            ln.descuento_prov_pct_2 = v_d2
                            cambio = True
                            changed_fields.append('descuento_prov_pct_2')
                        if v_d3 is not None and v_d3 != ln.descuento_prov_pct_3:
                            self._dbg(f"  -> CAMBIANDO d3 de {ln.descuento_prov_pct_3} a {v_d3}")
                            ln.descuento_prov_pct_3 = v_d3
                            cambio = True
                            changed_fields.append('descuento_prov_pct_3')

                        m_si = request.POST.get(f'sugerido_interno_{pid}')
                        v_si = _dec_local(m_si)
                        
                        # USUARIOS INTERNOS: Pueden editar sugerido_interno sin restricciones de clasificación
                        if v_si is not None and editable_interno and v_si != ln.sugerido_interno:
                            ln.sugerido_interno = v_si
                            cambio = True
                            changed_fields.append('sugerido_interno')

                        m_clas = request.POST.get(f'clasificacion_{pid}')
                        if m_clas is not None:
                            v_clas = (m_clas or '').strip().upper()
                            # VALIDACIÓN: Solo permitir cambiar clasificación C si tiene permiso
                            cla_actual = (ln.clasificacion or '').strip().upper()
                            if v_clas == 'C' and not puede_editar_clasificacion_c:
                                self._dbg(f"  -> Usuario no puede establecer clasificación C en línea {pid}")
                                continue
                            if cla_actual == 'C' and v_clas != 'C' and not puede_editar_clasificacion_c:
                                self._dbg(f"  -> Usuario no puede cambiar clasificación C existente en línea {pid}")
                                continue
                            
                            if v_clas != cla_actual:
                                ln.clasificacion = v_clas
                                cambio = True
                                changed_fields.append('clasificacion')
                                # CAMBIO: Solo forzar a 0 si la nueva clasificación es I (NO C)
                                if v_clas == 'I':
                                    if ln.sugerido_interno != Decimal("0"):
                                        ln.sugerido_interno = Decimal("0")
                                        if 'sugerido_interno' not in changed_fields:
                                            changed_fields.append('sugerido_interno')
                                    if ln.nuevo_sugerido_prov != Decimal("0"):
                                        ln.nuevo_sugerido_prov = Decimal("0")
                                        if 'nuevo_sugerido_prov' not in changed_fields:
                                            changed_fields.append('nuevo_sugerido_prov')

                    if cambio:
                        self._dbg(f"  Cambios en {pid}: {changed_fields}")
                        try:
                            ln.save(update_fields=list(set(changed_fields)))
                            actualizados += 1
                        except ValidationError as e:
                            errores_validacion.append(f"Línea {pid} ({ln.codigo_articulo}): {'; '.join(e.messages)}")
                            self._dbg(f"  Error validación en {pid}: {e}")
                    else:
                        self._dbg(f"  Sin cambios aplicables en {pid}.")

            if actualizados:
                self.message_user(request, f"{actualizados} línea(s) actualizada(s).", level=messages.SUCCESS)
            if errores_validacion:
                for error in errores_validacion:
                    self.message_user(request, f"Error de validación: {error}", level=messages.WARNING)
            if not actualizados and not errores_validacion:
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

            # Integración de KPIs de inventario (kpi_utils)
            # Integración de KPIs de inventario (kpi_utils)
            if lote_id:
                try:
                    # VERIFICACIÓN DE ANTIGÜEDAD DE KPIs
                    # Si la última actualización fue hace más de 1 día, refrescar desde ICG
                    if not request.GET.get('no_refresh'): # Flag por si queremos evitar bucle
                        lote_obj_kpi = SugeridoLote.objects.only('fecha_actualizacion_kpis').get(pk=lote_id)
                        last_update = lote_obj_kpi.fecha_actualizacion_kpis
                        
                        should_update = False
                        if not last_update:
                            should_update = True
                        else:
                            # timezone.now() utiliza la zona horaria activa si USE_TZ=True
                            if (timezone.now() - last_update) > timedelta(days=1):
                                should_update = True
                        
                        if should_update:
                            try:
                                print(f"Autof-refrescando KPIs para lote {lote_id} (última: {last_update})")
                                res_msg = actualizar_kpis_lote(int(lote_id))
                                self.message_user(request, f"Kpis Refrescados: {res_msg}", level=messages.INFO)
                            except Exception as e_upd:
                                print(f"Error al auto-actualizar KPIs: {e_upd}")
                                # No bloqueamos la vista si falla ICG

                    kpis_inv = obtener_kpis_por_lote(int(lote_id))
                    kpis.update(kpis_inv)
                except Exception as e:
                    print(f"Error calculando KPIs de inventario: {e}")

            response.context_data["kpis"] = kpis

            articulos_pivot = {}
            almacenes_set = set()
            for ln in qs:
                key = ln.codigo_articulo
                if key not in articulos_pivot:
                    articulos_pivot[key] = {
                        'lineas': {},
                        'costo_total': Decimal("0"),
                        'clasificacion': None  # Agregar campo para clasificación
                    }
                articulos_pivot[key]['lineas'][ln.nombre_almacen] = ln
                
                # Capturar la primera clasificación no vacía que encontremos
                if not articulos_pivot[key]['clasificacion'] and ln.clasificacion:
                    articulos_pivot[key]['clasificacion'] = ln.clasificacion.strip().upper()
                
                # Calcular costo basado en sugerido_interno (o sugerido_calculado si no hay interno)
                cantidad = ln.sugerido_interno if ln.sugerido_interno and ln.sugerido_interno > 0 else (ln.sugerido_calculado or Decimal("0"))
                costo_linea_calculado = cantidad * (ln.ultimo_costo or Decimal("0"))
                articulos_pivot[key]['costo_total'] += costo_linea_calculado
                
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
            puede_editar_sugerido_interno = es_interno  # Los internos siempre pueden editar su sugerido
            
            if lote_id:
                try:
                    lote_obj = SugeridoLote.objects.only('estado').get(pk=lote_id)
                    lote_estado = lote_obj.estado
                    inputs_disabled = (str(lote_estado).upper() == 'COMPLETADO')
                    es_vendedor_grupo = request.user.groups.filter(name='perfil_vendedor').exists()
                    if es_vendedor_grupo and str(lote_estado).upper() in {'CONFIRMADO', 'COMPLETADO'}:
                        inputs_disabled = True
                    
                    # Los internos pueden editar sugerido_interno incluso si está confirmado
                    if es_interno and str(lote_estado).upper() in {'CONFIRMADO'}:
                        puede_editar_sugerido_interno = True
                        
                    response.context_data['ocultar_boton_confirmar_proveedor'] = str(lote_estado).upper() in {'CONFIRMADO', 'COMPLETADO'}
                except SugeridoLote.DoesNotExist:
                    response.context_data['ocultar_boton_confirmar_proveedor'] = False

            response.context_data['lote_estado'] = lote_estado
            response.context_data['inputs_disabled'] = inputs_disabled
            response.context_data['puede_editar_sugerido_interno'] = puede_editar_sugerido_interno

            return response
        finally:
            self.list_editable = original_editable

    def get_descripcion_corta(self, obj):
        txt = getattr(obj, 'descripcion', '') or ''
        return txt if len(txt) <= 50 else txt[:47] + '…'
    get_descripcion_corta.short_description = "Descripción"