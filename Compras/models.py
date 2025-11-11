from django.utils import timezone
from decimal import Decimal
from django.db import models
from django.contrib.auth import get_user_model
from auditlog.registry import auditlog

User = get_user_model()

class ReglaClasificacion(models.Model):
    CLASE_CHOICES = [
        ('A', 'Clase A'),
        ('B', 'Clase B'),
        ('C', 'Clase C'),
        ('D', 'Clase D'),
        ('E', 'Clase E'),
    ]

    clase = models.CharField(max_length=1, choices=CLASE_CHOICES)
    umbral_minimo = models.DecimalField(max_digits=5, decimal_places=2)
    umbral_maximo = models.DecimalField(max_digits=5, decimal_places=2)
    activa = models.BooleanField(default=True)
    orden = models.PositiveIntegerField(default=0, help_text="Prioridad de la regla")

    def __str__(self):
        return f"{self.clase}: {self.umbral_minimo} - {self.umbral_maximo} ({'Activa' if self.activa else 'Inactiva'})"

    class Meta:
        verbose_name = "Regla de Clasificación"
        verbose_name_plural = "Reglas de Clasificación"
        unique_together = ('clase', 'umbral_minimo', 'umbral_maximo')
        ordering = ['orden', 'umbral_minimo']
auditlog.register(ReglaClasificacion)

class ProcesoClasificacion(models.Model):
    fecha_inicio = models.DateTimeField(auto_now_add=True)
    usuario = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True
    )
    estado = models.CharField(
        max_length=20,
        choices=[
            ('extraccion', 'Extracción'),
            ('procesado', 'Procesado'),
            ('edicion', 'Edición'),
            ('confirmado', 'Confirmado'),
            ('actualizado', 'Actualizado en ICG')
        ],
        default='extraccion'
    )
    descripcion = models.TextField(blank=True)

    def __str__(self):
        return f"Proceso #{self.pk} - {self.fecha_inicio:%Y-%m-%d %H:%M} - {self.estado}"
    class Meta:
        verbose_name = "Proceso de Clasificación"
        verbose_name_plural = "Procesos de Clasificación"
        ordering = ['-fecha_inicio']
auditlog.register(ProcesoClasificacion)

# 1. Tabla de artículos extraídos, sin edición
class ArticuloClasificacionTemporal(models.Model):
    proceso = models.ForeignKey(
        ProcesoClasificacion,
        on_delete=models.CASCADE,
        related_name='articulos_temporales',
        blank=True, null=True
    )
    codigo = models.CharField(max_length=100)
    departamento = models.CharField(max_length=200, blank=True, null=True)
    seccion = models.CharField(max_length=200, blank=True, null=True)
    familia = models.CharField(max_length=200, blank=True, null=True)
    subfamilia = models.CharField(max_length=200, blank=True, null=True)
    marca = models.CharField(max_length=200, blank=True, null=True)
    descripcion = models.CharField(max_length=200,blank=True, null=True)
    descat = models.CharField(max_length=100, blank=True, null=True)
    tipo = models.CharField(max_length=100, blank=True, null=True)
    referencia = models.CharField(max_length=50, blank=True, null=True)
    clasificacion = models.CharField(max_length=100, blank=True, null=True)
    clasificacion2 = models.CharField(max_length=100, blank=True, null=True)
    clasificacion3 = models.CharField(max_length=100, blank=True, null=True)
    clasificacion5 = models.CharField(max_length=100, blank=True, null=True)
    unidades_compras = models.FloatField(blank=True, null=True)
    importe_compras = models.CharField(max_length=200, blank=True, null=True)
    unidades = models.FloatField(blank=True, null=True)
    coste = models.CharField(max_length=200, blank=True, null=True)
    beneficio = models.CharField(max_length=200, blank=True, null=True)
    importe = models.CharField(max_length=200, blank=True, null=True)
    porcentaje_sv = models.CharField(max_length=100, blank=True, null=True)
    stock_actual = models.FloatField(blank=True, null=True)
    valoracion_stock_actual = models.CharField(max_length=200, blank=True, null=True)
    almacen = models.CharField(max_length=100, blank=True, null=True)
    estado_nuevo = models.CharField(max_length=100, blank=True, null=True)

    def __str__(self):
        return f"{self.codigo} - {self.descripcion}"

    class Meta:
        verbose_name = "Artículo Clasificación Temporal"
        verbose_name_plural = "Artículos Clasificación Temporal"
auditlog.register(ArticuloClasificacionTemporal)
# 2. Tabla de artículos en proceso, editables 
class ArticuloClasificacionProcesado(models.Model):
    """Tabla para artículos que han pasado por el proceso de clasificación y están en edición."""
    choises_clasificacion = (
        ('A', 'A'),
        ('B', 'B'),
        ('C', 'C'),
        ('E', 'E'),)
    proceso = models.ForeignKey(
        ProcesoClasificacion,
        on_delete=models.CASCADE,
        related_name='articulos_procesados'
    )
    seccion = models.CharField(max_length=100)
    codigo = models.CharField(max_length=20)
    descripcion = models.CharField(max_length=255, blank=True, null=True)
    referencia = models.CharField(max_length=30, blank=True, null=True)
    marca = models.CharField(max_length=100, blank=True, null=True)
    clasificacion_actual = models.CharField(max_length=5, blank=True, null=True)
    suma_importe = models.DecimalField(max_digits=12, decimal_places=2, blank=True, null=True)
    suma_unidades = models.IntegerField(blank=True, null=True)
    porcentaje_acumulado = models.DecimalField(max_digits=7, decimal_places=3, blank=True, null=True)
    nueva_clasificacion = models.CharField(max_length=5, blank=True, null=True, choices=choises_clasificacion)  # editable
    confirmado = models.BooleanField(default=False)  # Wizard step: confirmación
    almacen = models.CharField(max_length=100, blank=True, null=True)  # Almacén asociado
    importe_num = models.DecimalField(
        max_digits=25, decimal_places=2, blank=True, null=True,
        help_text="Valor de venta del artículo, si aplica",
        verbose_name="Importe Post"
    )

    fecha_creacion = models.DateTimeField(auto_now_add=True)
    fecha_actualizacion = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Artículo Clasificación Procesado"
        verbose_name_plural = "Artículos Clasificación Procesados"

    def __str__(self):
        return f"{self.seccion} - {self.codigo} - {self.descripcion}"
auditlog.register(ArticuloClasificacionProcesado)
# 3. Tabla final, con estado de acción y validación
class ArticuloClasificacionFinal(models.Model):
    proceso = models.ForeignKey(
        ProcesoClasificacion, on_delete=models.CASCADE, related_name='articulos_finales'
    )
    seccion = models.CharField(max_length=100)
    codigo = models.CharField(max_length=20)
    descripcion = models.CharField(max_length=255, blank=True, null=True)
    referencia = models.CharField(max_length=30, blank=True, null=True)
    marca = models.CharField(max_length=100, blank=True, null=True)
    clasificacion_actual = models.CharField(max_length=5, blank=True, null=True)
    nueva_clasificacion = models.CharField(max_length=5, blank=True, null=True)
    resultado_validacion = models.BooleanField()  # VERDADERO/FALSO
    almacen = models.CharField(max_length=100, blank=True, null=True) 

    estado_accion = models.CharField(
        max_length=30,
        choices=[("PENDIENTE", "Pendiente"), ("ACTUALIZADO", "Actualizado"), ("ERROR", "Error")],
        default="PENDIENTE"
    )
    mensaje_accion = models.TextField(blank=True, null=True)  # log o mensaje de error/success

    fecha_ejecucion = models.DateTimeField(auto_now_add=True)
    usuario = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True
    )

    class Meta:
        verbose_name = "Artículo Clasificación Final"
        verbose_name_plural = "Artículos Clasificación Final"

    def __str__(self):
        return f"{self.seccion} - {self.codigo} - {self.descripcion}"
auditlog.register(ArticuloClasificacionFinal)

#Proceso de c pedido de compras

class Proveedor(models.Model):
    nombre = models.CharField(max_length=255, unique=True)
    nit = models.CharField(max_length=32, blank=True, null=True)
    email_contacto = models.EmailField(blank=True, null=True)
    activo = models.BooleanField(default=True)
    cod_icg = models.CharField(max_length=50, blank=True, null=True, help_text="Código del proveedor en ICG")
    # Nuevo: presupuesto mensual asignado al proveedor
    presupuesto_mensual = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"), help_text="Presupuesto mensual de compras asignado a este proveedor")
    class Meta:
        verbose_name = "Proveedor"
        verbose_name_plural = "Proveedores"

    def __str__(self):
        return self.nombre
auditlog.register(Proveedor)

class Marca(models.Model):
    nombre = models.CharField(max_length=255, unique=True)

    class Meta:
        verbose_name = "Marca"
        verbose_name_plural = "Marcas"

    def __str__(self):
        return self.nombre


class VendedorPerfil(models.Model):
    """Vincula un usuario interno como 'vendedor' (para sub-agrupación por marca)."""
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="perfil_vendedor")
    alias = models.CharField(max_length=120, blank=True, null=True)

    class Meta:
        verbose_name = "Vendedor"
        verbose_name_plural = "Vendedores"

    def __str__(self):
        return self.alias or str(self.user)
auditlog.register(VendedorPerfil)

class AsignacionMarcaVendedor(models.Model):
    """Qué vendedor atiende qué marca para un proveedor."""
    proveedor = models.ForeignKey(Proveedor, on_delete=models.CASCADE, related_name="asignaciones")
    marca = models.ForeignKey(Marca, on_delete=models.CASCADE, related_name="asignaciones")
    vendedor = models.ForeignKey(VendedorPerfil, on_delete=models.CASCADE, related_name="asignaciones")

    class Meta:
        unique_together = [("proveedor", "marca", "vendedor")]
        verbose_name = "Asignación Marca ↔ Vendedor"
        verbose_name_plural = "Asignaciones Marca ↔ Vendedor"

    def __str__(self):
        return f"{self.proveedor} · {self.marca} → {self.vendedor}"
auditlog.register(AsignacionMarcaVendedor)

class ProveedorUsuario(models.Model):
    """
    Relación entre usuarios (externos o internos) y proveedores.
    Un usuario puede estar vinculado a varios proveedores.
    """
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="perfiles_proveedor")
    proveedor = models.ForeignKey(Proveedor, on_delete=models.CASCADE, related_name="usuarios")

    class Meta:
        verbose_name = "Perfil de Proveedor (Usuario)"
        verbose_name_plural = "Perfiles de Proveedor (Usuarios)"
        unique_together = ("user", "proveedor")  # evita duplicados exactos

    def __str__(self):
        return f"{self.user} → {self.proveedor}"
auditlog.register(ProveedorUsuario)

# ─────────────────────────────────────────────────────────────────────────────
# Lotes y Líneas de Sugerido
# ─────────────────────────────────────────────────────────────────────────────

class SugeridoLote(models.Model):
    class Estado(models.TextChoices):
        PENDIENTE = "PENDIENTE", "Pendiente"
        ENVIADO = "ENVIADO", "Enviado a proveedor"
        CONFIRMADO = "CONFIRMADO", "Confirmado por proveedor"
        COMPLETADO = "COMPLETADO", "Completado/Orden generada"
        ANULADO = "ANULADO", "Anulado"

    nombre = models.CharField(max_length=255, help_text="Identificador legible del lote (e.g. Sugerido 2025-08 corte semanal)")
    marca = models.ForeignKey(Marca, on_delete=models.SET_NULL, null=True, blank=True, related_name="lotes", help_text="Marca asociada del sugerido")
    proveedor = models.ForeignKey(Proveedor, on_delete=models.PROTECT, related_name="lotes", null=True, blank=True , help_text="Proveedores disponibles para esa marca")
    fecha_extraccion = models.DateTimeField(default=timezone.now, db_index=True)
    estado = models.CharField(max_length=20, choices=Estado.choices, default=Estado.PENDIENTE, db_index=True)
    clasificacion_filtro = models.CharField(max_length=50, blank=True, null=True, help_text="Si se filtró por A/B/C/I u otra etiqueta.")
    creado_por = models.ForeignKey(User, on_delete=models.PROTECT, related_name="lotes_creados")

    total_lineas = models.PositiveIntegerField(default=0)
    total_costo = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    pedidos_icg = models.JSONField(
        default=list, blank=True, null=True,
        help_text="Listado de pedidos ICG generados por almacén (JSON)."
    )
    observaciones = models.TextField(blank=True, null=True)
    numserie = models.CharField(max_length=10, blank=True, null=True, help_text="Número de serie para pedidos en ICG")
    numpedido = models.CharField(max_length=20, blank=True, null=True, help_text="Número de pedido actual en ICG (se autoincrementa al importar)")
    subserie = models.CharField(max_length=5, blank=True, null=True, help_text="Subserie para pedidos en ICG")

    class Meta:
        ordering = ["-fecha_extraccion"]
        verbose_name = "Lote de Sugerido"
        verbose_name_plural = "Lotes de Sugerido"

    def __str__(self):
        return f"Lote #{self.pk} · {self.nombre}"

    def recomputar_totales(self):
        agg = self.lineas.aggregate(
            n=models.Count("id"),
            cost=models.Sum(models.F("costo_linea"))
        )
        self.total_lineas = agg.get("n") or 0
        self.total_costo = agg.get("cost") or Decimal("0")

    def save(self, *args, **kwargs):
        is_new = self.pk is None
        super().save(*args, **kwargs)
        if is_new and self.marca:
            from Compras.services.icg_import import import_data_sugerido_inventario
            import_data_sugerido_inventario(user_id=self.creado_por_id, marca=self.marca.nombre, lote_id=self.pk, provedor=self.proveedor.nombre)
            # NUEVO: notificar vendedor asignado (si hay proveedor y marca)
            if self.proveedor and self.marca:
                try:
                    from Compras.services.notifications import notificar_vendedor_lote_asignado
                    notificar_vendedor_lote_asignado(proveedor=self.proveedor, marca=self.marca, lote=self)
                except Exception:
                    pass
        # Recalcula totales luego del import y decide estado inicial
        self.recomputar_totales()
        update_fields = ["total_lineas", "total_costo"]
        if is_new:
            nuevo_estado = self.Estado.ENVIADO if self.total_lineas > 0 else self.Estado.PENDIENTE
            if self.estado != nuevo_estado:
                self.estado = nuevo_estado
                update_fields.append("estado")
        super().save(update_fields=update_fields)
auditlog.register(SugeridoLote)

class SugeridoLinea(models.Model):
    class EstadoLinea(models.TextChoices):
        PENDIENTE = "PENDIENTE", "Pendiente"
        ENVIADA_PROV = "ENVIADA_PROV", "Enviada a proveedor"
        RESPONDIDA = "RESPONDIDA", "Respondida por proveedor"
        APROBADA = "APROBADA", "Aprobada por compras"
        RECHAZADA = "RECHAZADA", "Rechazada"
        ORDENADA = "ORDENADA", "Orden generada"

    # relación y metadatos
    lote = models.ForeignKey(SugeridoLote, on_delete=models.CASCADE, related_name="lineas")
    proveedor = models.ForeignKey(Proveedor, on_delete=models.PROTECT, related_name="lineas_sugerido")
    marca = models.ForeignKey(Marca, on_delete=models.SET_NULL, null=True, blank=True, related_name="lineas_sugerido")
    vendedor = models.ForeignKey(VendedorPerfil, on_delete=models.SET_NULL, null=True, blank=True, related_name="lineas_sugerido")

    cod_almacen = models.CharField(max_length=20, db_index=True)
    nombre_almacen = models.CharField(max_length=120)

    codigo_articulo = models.CharField(max_length=64, db_index=True)
    referencia = models.CharField(max_length=128, blank=True, null=True)
    descripcion = models.CharField(max_length=255)
    departamento = models.CharField(max_length=120, blank=True, null=True)
    seccion = models.CharField(max_length=120, blank=True, null=True)
    familia = models.CharField(max_length=120, blank=True, null=True)
    subfamilia = models.CharField(max_length=120, blank=True, null=True)
    tipo = models.CharField(max_length=50, blank=True, null=True)

    # clasificación ABCI (o libre)
    clasificacion = models.CharField(max_length=20, blank=True, null=True, db_index=True)

    # indicadores operativos
    stock_actual = models.DecimalField(max_digits=16, decimal_places=2, default=Decimal("0"))
    stock_minimo = models.DecimalField(max_digits=16, decimal_places=2, default=Decimal("0"))
    stock_maximo = models.DecimalField(max_digits=16, decimal_places=2, default=Decimal("0"))
    lead_time_dias = models.PositiveIntegerField(default=0)
    stock_seguridad = models.DecimalField(max_digits=16, decimal_places=2, default=Decimal("0"), help_text="Si no se usa, igual a stock_minimo")

    # empaque / costo
    uds_compra_base = models.PositiveIntegerField(default=1)
    uds_compra_mult = models.PositiveIntegerField(default=1)
    embalaje = models.PositiveIntegerField(default=1)  # calculado/base*mult
    ultimo_costo = models.DecimalField(max_digits=18, decimal_places=4, default=Decimal("0"))

    # sugerido calculado desde SQL de extracción
    sugerido_base = models.DecimalField(max_digits=16, decimal_places=2, default=Decimal("0"))
    factor_almacen = models.DecimalField(max_digits=6, decimal_places=2, default=Decimal("1.00"))
    sugerido_calculado = models.DecimalField(max_digits=16, decimal_places=2, default=Decimal("0"))
    cajas_calculadas = models.DecimalField(max_digits=16, decimal_places=2, default=Decimal("0"))
    costo_linea = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0"))

    # edición interna (compras)
    sugerido_interno = models.DecimalField(max_digits=16, decimal_places=2, default=Decimal("0"), help_text="Editable por Responsable de Compras")
    comentario_interno = models.CharField(max_length=500, blank=True, null=True)

    # respuesta del proveedor (editable según clasificación)
    continuidad_activo = models.BooleanField(default=True, help_text="Activo/Descontinuado según proveedor")
    nuevo_sugerido_prov = models.DecimalField(max_digits=16, decimal_places=2, default=Decimal("0"))
    descuento_prov_pct = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("0.00"))
    # --- Nuevos descuentos adicionales secuenciales ---
    descuento_prov_pct_2 = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("0.00"), help_text="Segundo descuento proveedor % (se aplica tras el primero)")
    descuento_prov_pct_3 = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("0.00"), help_text="Tercer descuento proveedor % (se aplica tras el segundo)")
    nuevo_nombre_prov = models.CharField(max_length=255, blank=True, null=True)
    observaciones_prov = models.CharField(max_length=500, blank=True, null=True)
    # Presupuesto (monto meta costo proveedor para esta línea – opcional)
    presupuesto_proveedor = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"), help_text="Presupuesto meta de compra (costo) para esta línea")

    estado_linea = models.CharField(max_length=20, choices=EstadoLinea.choices, default=EstadoLinea.PENDIENTE, db_index=True)

    creado = models.DateTimeField(auto_now_add=True)
    actualizado = models.DateTimeField(auto_now=True)

    warning_no_multiplo = models.BooleanField(default=False)
    warning_incremento_100 = models.BooleanField(default=False)
    IVA = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("0.00"), help_text="IVA aplicable al artículo (%)")
    cod_proveedor = models.CharField(max_length=50, blank=True, null=True, help_text="Código del artículo según el proveedor")
    es_informativa = models.BooleanField(default=False, help_text="Si la línea es solo informativa (no se ordena)")
    Proveedor_principal = models.CharField(max_length=5, blank=True, null=True, help_text="Define si el proveedor principal para el artículo (S/N)")
    clasificacion_original = models.CharField(max_length=20, blank=True, null=True, help_text="Clasificación original al momento de la extracción")

    class Meta:
        indexes = [
            models.Index(fields=["lote", "proveedor"]),
            models.Index(fields=["proveedor", "marca"]),
            models.Index(fields=["clasificacion"]),
        ]
        
        verbose_name = "Línea de Sugerido"
        verbose_name_plural = "Líneas de Sugerido"

# ─── Helpers de permisos por clasificación ───────────────────────
    @property
    def clasif_upper(self) -> str:
        return (self.clasificacion or "").strip().upper()

    def editable_por_proveedor(self) -> bool:
        return self.clasif_upper in {"A", "B"}

    def editable_por_interno(self) -> bool:
        # internos (Mercasur) editan A, B, C ; I bloqueado
        return self.clasif_upper in {"A", "B", "C"}

    # ─── KPIs / costo / validaciones ────────────────────────────────
    @property
    def cantidad_a_ordenar(self) -> Decimal:
        """Preferir sugerido_interno si >0; si no, sugerido_calculado."""
        return (self.sugerido_interno or Decimal("0")) or (self.sugerido_base or Decimal("0"))

    @property
    def desviacion_seguridad_pct(self) -> Decimal:
        base = self.stock_seguridad or self.stock_minimo or Decimal("0")
        if base and base != 0:
            return ((self.stock_actual - base) / base) * Decimal("100")
        return Decimal("0")

    def _es_multiplo(self, valor: Decimal) -> bool:
        empa = int(self.embalaje or 1)
        if empa <= 0:
            return True
        try:
            return (Decimal(valor) % Decimal(empa)) == 0
        except Exception:
            return True

    def recomputar_costos(self):
        qty = self.cantidad_a_ordenar
        self.costo_linea = (qty or Decimal("0")) * (self.ultimo_costo or Decimal("0"))

    def clean(self):
        # sugeridos no negativos
        if self.sugerido_interno is not None and self.sugerido_interno < 0:
            raise models.ValidationError("El sugerido interno no puede ser negativo.")
        if self.nuevo_sugerido_prov is not None and self.nuevo_sugerido_prov < 0:
            raise models.ValidationError("El nuevo sugerido del proveedor no puede ser negativo.")
        if self.descuento_prov_pct and self.descuento_prov_pct < 0:
            raise models.ValidationError("El descuento proveedor no puede ser negativo.")
        if self.descuento_prov_pct_2 and self.descuento_prov_pct_2 < 0:
            raise models.ValidationError("El segundo descuento proveedor no puede ser negativo.")
        if self.descuento_prov_pct_3 and self.descuento_prov_pct_3 < 0:
            raise models.ValidationError("El tercer descuento proveedor no puede ser negativo.")

        # advertencia (no bloqueo) si no múltiplo de embalaje
        self.warning_no_multiplo = False
        candidato = self.sugerido_interno or self.nuevo_sugerido_prov or Decimal("0")
        if candidato and not self._es_multiplo(candidato):
            self.warning_no_multiplo = True

  
        # stock de seguridad default
        if not self.stock_seguridad or self.stock_seguridad == 0:
            self.stock_seguridad = self.stock_minimo or Decimal("0")

    def save(self, *args, **kwargs):
        
        self.clean()
        
        # Si la clasificación es I o C, forzar sugerido_interno a 0
        cla_upper = (self.clasificacion or '').strip().upper()
        if cla_upper in {'I', 'C'}:
            self.sugerido_interno = Decimal("0")
        # Si es una línea nueva y no tiene sugerido_interno, calcularlo inteligentemente
        elif not self.pk and (not self.sugerido_interno or self.sugerido_interno == 0):
            from Compras.services.calculo_sugerido import calcular_sugerido_inteligente
            self.sugerido_interno = calcular_sugerido_inteligente(
                stock_actual=self.stock_actual,
                stock_maximo=self.stock_maximo,
                embalaje=self.embalaje
            )
        
        self.recomputar_costos()
        super().save(*args, **kwargs)
auditlog.register(SugeridoLinea)

# ─────────────────────────────────────────────────────────────────────
# Respuesta del proveedor (lote de modificaciones) y confirmación
# ─────────────────────────────────────────────────────────────────────

class SugeridoLineaCambio(models.Model):
    """Snapshot de cambios enviados por el proveedor (retransmisión)."""
    linea = models.ForeignKey(SugeridoLinea, on_delete=models.CASCADE, related_name="cambios")
    fecha = models.DateTimeField(default=timezone.now)
    usuario = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)

    continuidad_activo = models.BooleanField(default=True)
    nuevo_sugerido_prov = models.DecimalField(max_digits=16, decimal_places=2, default=Decimal("0"))
    descuento_prov_pct = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("0.00"))
    nuevo_nombre_prov = models.CharField(max_length=255, blank=True, null=True)
    observaciones_prov = models.CharField(max_length=500, blank=True, null=True)

    class Meta:
        ordering = ["-fecha"]
        verbose_name = "Cambio de Sugerido (Proveedor)"
        verbose_name_plural = "Cambios de Sugerido (Proveedor)"
auditlog.register(SugeridoLineaCambio)
# ─────────────────────────────────────────────────────────────────────
# Orden de compra / historial y logs de integración ICG
# ─────────────────────────────────────────────────────────────────────


class OrdenCompra(models.Model):
    """Documento interno (previo a ICG) que se puede exportar y sincronizar con ICG."""
    lote = models.ForeignKey(SugeridoLote, on_delete=models.PROTECT, related_name="ordenes")
    proveedor = models.CharField(max_length=255, db_index=True)
    cod_almacen = models.CharField(max_length=20)
    nombre_almacen = models.CharField(max_length=120)

    numero_orden = models.CharField(max_length=50, unique=True)
    fecha = models.DateTimeField(default=timezone.now)
    costo_total = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))

    id_orden_icg = models.CharField(max_length=80, blank=True, null=True, help_text="Identificador devuelto por ICG")
    generado_por = models.ForeignKey(User, on_delete=models.PROTECT, related_name="ordenes_generadas")

    class Meta:
        ordering = ["-fecha"]
        verbose_name = "Orden de Compra"
        verbose_name_plural = "Órdenes de Compra"

    def __str__(self):
        return f"OC {self.numero_orden} · {self.proveedor} · {self.nombre_almacen}"
auditlog.register(OrdenCompra)

class OrdenCompraLinea(models.Model):
    orden = models.ForeignKey(OrdenCompra, on_delete=models.CASCADE, related_name="lineas")
    codigo_articulo = models.CharField(max_length=64)
    descripcion = models.CharField(max_length=255)
    embalaje = models.PositiveIntegerField(default=1)
    cantidad = models.DecimalField(max_digits=16, decimal_places=2, default=Decimal("0"))
    costo_unitario = models.DecimalField(max_digits=18, decimal_places=4, default=Decimal("0"))
    costo_total = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0"))
    clasificacion = models.CharField(max_length=20, blank=True, null=True)

    class Meta:
        verbose_name = "Línea de OC"
        verbose_name_plural = "Líneas de OC"

class OrdenICGLog(models.Model):
    orden = models.ForeignKey(OrdenCompra, on_delete=models.CASCADE, related_name="logs")
    fecha = models.DateTimeField(default=timezone.now)
    accion = models.CharField(max_length=50, default="enviar_icg")
    exito = models.BooleanField(default=False)
    id_orden_icg = models.CharField(max_length=80, blank=True, null=True)
    mensaje = models.TextField(blank=True, null=True)
    payload = models.JSONField(blank=True, null=True)

    class Meta:
        ordering = ["-fecha"]
        verbose_name = "Log Integración ICG"
        verbose_name_plural = "Logs Integración ICG"