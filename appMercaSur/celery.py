import os
from celery import Celery
from celery.schedules import crontab
# Configurar Celery con Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'appMercaSur.settings')

app = Celery('appMercaSur')
app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks()
