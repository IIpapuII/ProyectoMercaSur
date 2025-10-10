from decimal import Decimal, getcontext
from itertools import groupby
from operator import attrgetter

from django.db.models import F, Value, CharField, FloatField, Case, When
from django.db.models.functions import Cast, Replace

from .models import (
    ProcesoClasificacion,
    ArticuloClasificacionTemporal,
    ArticuloClasificacionProcesado,
    ReglaClasificacion,
    ArticuloClasificacionFinal
)
from django.contrib.sites.models import Site
import io
import pandas as pd
# Ajustar precisión si es necesario
getcontext().prec = 6

DEPARTAMENTOS_EXCLUIDOS = [
    'BONOS MERCASUR', 'BONOS PROVEEDORES', 'CARTERA', 'CONCESION CARNES',
    'CONCESION DISTRAVES', 'CONTABILIDAD', 'GASTOS NO USAR',
    'INGRESOS NO USAR', 'REDENCION DE PUNTOS', 'BOLSAS USO INTERNO'
]
MARCAS_EXCLUIDAS = [
    'MERCASUR FRUVER', 'MERCASUR PANADERIA', 'BOCADILLOS CATICA CONSIGN',
    'UNBROKEN CONSIGNACION', 'UMBROKEN MASCOTAS CONSIGN'
]
CLASIFICACION_EXCLUIDAS = ['I']

def calcular_clasificacion(acumulado: float, unidades: float):
    reglas = ReglaClasificacion.objects.filter(activa=True).order_by('orden')
    for regla in reglas:
        if regla.umbral_minimo <= acumulado < regla.umbral_maximo:
            return regla.clase
    return 'C'

def get_campo_clasificacion_por_almacen(almacen):
    almacen = (almacen or '').upper()
    return {
        'MERCASUR CALDAS':   'CLASIFICACION',
        'MERCASUR CENTRO':   'CLASIFICACION2',
        'MERCASUR CABECERA': 'CLASIFICACION3',
        'MERCASUR SOTOMAYOR':'CLASIFICACION5',
    }.get(almacen)

def get_clasificacion_actual(temp):
    """
    Devuelve la clasificación correspondiente al almacén.
    """
    almacen = (temp.almacen or '').upper()
    return {
        'MERCASUR CALDAS':   temp.clasificacion,
        'MERCASUR CENTRO':   temp.clasificacion2,
        'MERCASUR CABECERA': temp.clasificacion3,
        'MERCASUR SOTOMAYOR':temp.clasificacion5,
    }.get(almacen)


def procesar_clasificacion(proceso: ProcesoClasificacion):
    """
    Extrae de ArticuloClasificacionTemporal, filtra, calcula el porcentaje de cada artículo
    sobre el total de su sesión (sección+almacén) y el acumulado hasta 100%, y guarda en
    ArticuloClasificacionProcesado.
    """
    def _s(val):  # normaliza strings para ordenar/agrup
        return val or ""
    def _dec(val):  # convierte a Decimal de forma segura
        try:
            return Decimal(str(val)) if val is not None else Decimal("0")
        except Exception:
            return Decimal("0")

    qs = (
        ArticuloClasificacionTemporal.objects
        .filter(
            proceso=proceso,
            descat='F',
            departamento__isnull=False,
            almacen__isnull=False,
        )
        .exclude(departamento__in=DEPARTAMENTOS_EXCLUIDOS)
        .exclude(marca__in=MARCAS_EXCLUIDAS)
        .annotate(
            clasificacion_actual=Case(
                When(almacen__iexact='MERCASUR CALDAS',    then=F('clasificacion')),
                When(almacen__iexact='MERCASUR CENTRO',    then=F('clasificacion2')),
                When(almacen__iexact='MERCASUR CABECERA',  then=F('clasificacion3')),
                When(almacen__iexact='MERCASUR SOTOMAYOR', then=F('clasificacion5')),
                default=Value(None),
                output_field=CharField(),
            ),
            importe_clean=Replace(F('importe'), Value(','), Value('')),
            importe_num=Cast('importe_clean', FloatField()),
        )
        .filter(importe_num__gte=0)
        .exclude(clasificacion_actual__in=CLASIFICACION_EXCLUIDAS)
    )

    temporales = list(qs)
    temporales.sort(key=lambda t: (_s(t.seccion), _s(t.almacen), -_dec(t.importe_num)))

    for (seccion, almacen), group in groupby(temporales, key=lambda t: (_s(t.seccion), _s(t.almacen))):
        items = list(group)
        total = sum(_dec(t.importe_num) for t in items)
        acumulado = Decimal('0')

        # Si TODO el grupo no tiene ventas: todos quedan en E y no hay acumulado
        if total <= 0:
            for temp in items:
                ArticuloClasificacionProcesado.objects.update_or_create(
                    proceso=proceso,
                    codigo=_s(temp.codigo),
                    almacen=_s(temp.almacen),
                    defaults={
                        'seccion':               _s(temp.seccion),
                        'descripcion':           _s(temp.descripcion),
                        'referencia':            _s(temp.referencia),
                        'marca':                 _s(temp.marca),
                        'clasificacion_actual':  _s(temp.clasificacion_actual),
                        'suma_importe':          Decimal('0'),      # % del ítem
                        'importe_num':           _dec(temp.importe_num),
                        'suma_unidades':         int(temp.unidades or 0),
                        'porcentaje_acumulado':  Decimal('0'),
                        'nueva_clasificacion':   'E',
                    }
                )
            continue  # siguiente grupo

        # Con total > 0, ordena desc por importe y aplica la regla de importe=0 => E sin acumular
        for temp in sorted(items, key=lambda t: -_dec(t.importe_num)):
            importe_val = _dec(temp.importe_num)
            unidades_val = int(temp.unidades or 0)

            if importe_val <= 0:
                # No aporta porcentaje; no cambia el acumulado; clasifica como E
                pct = Decimal('0')
                porcentaje_acumulado = acumulado
                nueva_clas = 'E'
            else:
                pct = (importe_val / total * Decimal('100'))
                acumulado += pct
                porcentaje_acumulado = acumulado
                nueva_clas = calcular_clasificacion(porcentaje_acumulado, unidades_val)

            ArticuloClasificacionProcesado.objects.update_or_create(
                proceso=proceso,
                codigo=_s(temp.codigo),
                almacen=_s(temp.almacen),
                defaults={
                    'seccion':               _s(temp.seccion),
                    'descripcion':           _s(temp.descripcion),
                    'referencia':            _s(temp.referencia),
                    'marca':                 _s(temp.marca),
                    'clasificacion_actual':  _s(temp.clasificacion_actual),
                    'suma_importe':          pct,                 # % del ítem
                    'importe_num':           importe_val,
                    'suma_unidades':         unidades_val,
                    'porcentaje_acumulado':  porcentaje_acumulado,
                    'nueva_clasificacion':   _s(nueva_clas),
                }
            )

    proceso.estado = 'procesado'
    proceso.save(update_fields=['estado'])


from django.core.mail import EmailMultiAlternatives
from django.utils.html import strip_tags


def notificar_proceso_finalizado(proceso: ProcesoClasificacion, total: int):
    fecha = proceso.fecha_inicio.strftime('%d/%m/%Y %H:%M')
    asunto = f'🟢 Proceso de clasificación #{proceso.pk} Iniciado {fecha}'

    dominio = Site.objects.get_current().domain
    url_admin = f"https://{dominio}/admin/Compras/procesoclasificacion/"

    # HTML personalizado (puedes adaptarlo a una plantilla)
    html_content = f"""
    <div style="font-family: Arial, sans-serif; color: #333;">
        <div style="text-align: center; margin-bottom: 20px;">
            <img src="https://notificaciones.mercasur.com.co:9180/logo.png" alt="Mercasur" style="height: 70px;" />
        </div>

        <h2 style="color: #2ca646;">Proceso #{proceso.pk}  Iniciado</h2>

        <p>Hola,</p>

        <p>El proceso de clasificación en su etapa de extración <strong>#{proceso.pk}</strong> ha finalizado exitosamente con <strong>{total}</strong> artículos procesados.</p>

        <p>
            Puedes revisarlo directamente en el sistema desde el siguiente enlace:<br>
            <a href="{url_admin}" style="color: #2ca646; font-weight: bold;">Ver proceso en el panel de administración</a>
        </p>

        <hr style="margin-top: 30px;">
        <p style="font-size: 12px; color: #999;">Mercasur • Cada día mejor</p>
    </div>
    """

    text_content = strip_tags(html_content)  # fallback de texto plano

    destinatarios = [
        'gconectores@mercasur.com.co',
        'Gestrategadeportafolio@mercasur.com.co',
        'guerrerademarca@mercasur.com.co',
        'gresaltadores@mercasur.com.co',
        'desarrollador@mercasur.com.co'
    ]

    msg = EmailMultiAlternatives(
        subject=asunto,
        body=text_content,
        from_email='noreply@mercasur.com.co',
        to=destinatarios,
    )
    msg.attach_alternative(html_content, "text/html")
    msg.send()
    print(f"Notificación enviada: Proceso #{proceso.pk} con {total} artículos procesados.")


def notificar_proceso_con_excel(proceso, total):
    fecha = proceso.fecha_inicio.strftime('%d/%m/%Y %H:%M')
    asunto = f'🟢 Proceso #{proceso.pk} finalizado - Resultados adjuntos'
    
    dominio = Site.objects.get_current().domain
    url_admin = f"https://{dominio}/admin/Compras/procesoclasificacion/"

    # HTML
    html_content = f"""
    <div style="font-family: Arial, sans-serif; color: #333;">
        <div style="text-align: center; margin-bottom: 20px;">
            <img src="https://notificaciones.mercasur.com.co:9180/assets/logo.png" alt="Mercasur" style="height: 70px;" />
        </div>

        <h2 style="color: #2ca646;">Proceso #{proceso.pk} Finalizado</h2>
        <p>Hola,</p>
        <p>El proceso de clasificación <strong>#{proceso.pk}</strong> ha concluido con <strong>{total}</strong> artículos.</p>
        <p>
            Puedes verlo en el sistema desde:<br>
            <a href="{url_admin}" style="color: #2ca646; font-weight: bold;">Ver proceso en el panel de administración</a>
        </p>
        <p>Se adjunta un archivo Excel con los artículos clasificados.</p>
        <hr style="margin-top: 30px;">
        <p style="font-size: 12px; color: #999;">Mercasur • Cada día mejor</p>
    </div>
    """
    text_content = strip_tags(html_content)

    # Query filtrada por proceso
    qs = ArticuloClasificacionFinal.objects.filter(proceso=proceso).values(
        'seccion', 'codigo', 'descripcion', 'referencia',
        'marca', 'clasificacion_actual', 'nueva_clasificacion',
        'resultado_validacion', 'almacen'
    )

    # Generar archivo Excel en memoria
    df = pd.DataFrame(qs)
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False, sheet_name='Clasificación Final')
    output.seek(0)

    # Configurar correo
    destinatarios = [
        'gconectores@mercasur.com.co',
        'Gestrategadeportafolio@mercasur.com.co',
        'guerrerademarca@mercasur.com.co',
        'gresaltadores@mercasur.com.co',
        'desarrollador@mercasur.com.co'
    ]

    msg = EmailMultiAlternatives(
        subject=asunto,
        body=text_content,
        from_email='noreply@mercasur.com.co',
        to=destinatarios,
    )
    msg.attach_alternative(html_content, "text/html")
    msg.attach(f'clasificacion_final_proceso_{proceso.pk}.xlsx', output.read(), 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    msg.send()

    print(f"Correo enviado con Excel adjunto: Proceso #{proceso.pk}")



