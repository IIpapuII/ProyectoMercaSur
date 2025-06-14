from datetime import timedelta
from django.shortcuts import render

from django.contrib.admin.views.decorators import staff_member_required
from django.db.models import Count
from django.utils import timezone

from .models import Binnacle

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

    # Totales por categoría
    category_counts = (
        Binnacle.objects.values('equipment_service_category__name')
        .annotate(count=Count('id'))
        .order_by('equipment_service_category__name')
    )
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

    context = {
        'status_counts': status_counts,
        'total': total,
        'current_month': current_month,
        'today': today,
        'this_week': this_week,
        'en_proceso': en_proceso,
        'resueltos_mes': resueltos_mes,
        'category_counts': category_counts,
        'location_counts': location_counts,
        'category_service': category_service,
    }

    return render(request, 'SoporteTI/binnacle_dashboard.html', context)