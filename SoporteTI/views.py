from datetime import timedelta
from django.shortcuts import render
from django.http import JsonResponse
from django.contrib.admin.views.decorators import staff_member_required
from django.db.models import Count
from django.utils import timezone
from django.contrib.admin.sites import site as admin_site

from .models import Binnacle

from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.admin.sites import site as admin_site
from django.db.models import Count, Avg, F, ExpressionWrapper, DurationField
from django.utils import timezone
from datetime import timedelta

from .models import Binnacle, Equipment

@staff_member_required
def binnacle_dashboard(request):
    now = timezone.now()

    # Totales por estado
    status_counts = (
        Binnacle.objects.values('status')
        .annotate(count=Count('id'))
        .order_by('status')
    )

    # Totales globales
    total = Binnacle.objects.count()
    current_month = Binnacle.objects.filter(
        created_at__year=now.year,
        created_at__month=now.month
    ).count()
    today = Binnacle.objects.filter(created_at__date=now.date()).count()
    this_week = Binnacle.objects.filter(
        created_at__gte=now - timedelta(days=7)
    ).count()
    en_proceso = Binnacle.objects.filter(status="En Proceso").count()
    resueltos_mes = Binnacle.objects.filter(
        status="Resuelto",
        created_at__year=now.year,
        created_at__month=now.month
    ).count()

    # Tiempo promedio de resolución (solo resueltos y cancelados)
    time_to_resolve = Binnacle.objects.filter(
        status__in=["Resuelto", "Cancelado"],
        status_changed_at__isnull=False,
        fechaSolicitud__isnull=False
    ).annotate(
        resolution_time=ExpressionWrapper(
            F('status_changed_at') - F('fechaSolicitud'),
            output_field=DurationField()
        )
    ).aggregate(
        avg_resolution=Avg('resolution_time')
    )

    # Totales por categoría de equipo
    category_counts = (
        Binnacle.objects.values('equipment_service_category__name')
        .annotate(count=Count('id'))
        .order_by('equipment_service_category__name')
    )

    # Totales por categoría de incidencia
    category_service = (
        Binnacle.objects.values('Category__name_category')
        .annotate(count=Count('id'))
        .order_by('Category__name_category')
    )

    # Totales por ubicación
    location_counts = (
        Binnacle.objects.values('location__name')
        .annotate(count=Count('id'))
        .order_by('location__name')
    )

    # Tickets por técnico
    technician_counts = (
        Binnacle.objects.values('employee_service__first_name')
        .annotate(count=Count('id'))
        .order_by('employee_service__first_name')
    )

    # === Métricas de equipos ===
    total_equipment = Equipment.objects.count()
    equipment_by_status = (
        Equipment.objects.values('status')
        .annotate(count=Count('id'))
        .order_by('status')
    )
    equipment_by_category = (
        Equipment.objects.values('category__name')
        .annotate(count=Count('id'))
        .order_by('category__name')
    )
    equipment_by_location = (
        Equipment.objects.values('location_equipment__name')
        .annotate(count=Count('id'))
        .order_by('location_equipment__name')
    )
    equipment_by_assigned = (
        Equipment.objects.values('assigned_to__first_name')
        .annotate(count=Count('id'))
        .order_by('assigned_to__first_name')
    )
    # Edad promedio de equipos (años)
    equipment_avg_age = Equipment.objects.annotate(
        age=ExpressionWrapper(
            timezone.now().date() - F('purchase_date'),
            output_field=DurationField()
        )
    ).aggregate(
        avg_age_days=Avg('age')
    )
    avg_age_years = equipment_avg_age['avg_age_days'].days / 365 if equipment_avg_age['avg_age_days'] else None

    # Top equipos con más tickets
    top_equipment_issues = (
        Binnacle.objects.values('equipment_service_category__name')
        .annotate(count=Count('id'))
        .order_by('-count')[:5]
    )

    context = admin_site.each_context(request)
    context.update({
        # Soporte
        'status_counts': status_counts,
        'total': total,
        'current_month': current_month,
        'today': today,
        'this_week': this_week,
        'en_proceso': en_proceso,
        'resueltos_mes': resueltos_mes,
        'time_to_resolve': time_to_resolve['avg_resolution'],
        'category_counts': category_counts,
        'category_service': category_service,
        'location_counts': location_counts,
        'technician_counts': technician_counts,
        'top_equipment_issues': top_equipment_issues,

        # Equipos
        'total_equipment': total_equipment,
        'equipment_by_status': equipment_by_status,
        'equipment_by_category': equipment_by_category,
        'equipment_by_location': equipment_by_location,
        'equipment_by_assigned': equipment_by_assigned,
        'avg_age_years': round(avg_age_years, 2) if avg_age_years else None,
    })

    return render(request, 'SoporteTI/binnacle_dashboard.html', context)



@staff_member_required
def sugerencias_binnacle(request):
    top_sugerencias = (
        Binnacle.objects
        .values('description')
        .annotate(frecuencia=Count('id'))
        .order_by('-frecuencia')[:10]
    )
    return JsonResponse(list(top_sugerencias), safe=False)