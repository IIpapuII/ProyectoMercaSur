from django.urls import path

from . import views

urlpatterns = [
    path('prueba/', views.index, name='articulosMoficados'),
]