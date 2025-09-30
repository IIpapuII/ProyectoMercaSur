# Importaciones base comunes para todos los archivos admin
from django.contrib import admin
from django.urls import path, reverse
from django.utils.html import format_html
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect
from django.http import HttpResponse, StreamingHttpResponse
from django.forms import modelformset_factory
from django.utils.decorators import method_decorator
from django.contrib.admin.views.decorators import staff_member_required
from django.template.response import TemplateResponse
from django.db.models import Sum, Count, Case, When, F, Q, DecimalField, Exists, OuterRef
from django.db.models.functions import Coalesce
from django.db import transaction
from django.utils import timezone
from django.conf import settings
from django.core.mail import send_mail
from decimal import Decimal
import csv
from io import BytesIO
from openpyxl import Workbook

# Importaciones de utilidades del proyecto
from presupuesto.utils import formato_dinero_colombiano
from Compras.forms import NuevaClasificacionForm