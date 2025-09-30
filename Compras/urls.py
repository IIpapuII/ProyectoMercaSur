# urls.py
from django.urls import path
from django import forms
from django.contrib.admin.views.decorators import staff_member_required 
from . import views


urlpatterns = [
    path('api/marcas-por-proveedor/', views.api_marcas_por_proveedor, name='api_marcas_por_proveedor'),
]

