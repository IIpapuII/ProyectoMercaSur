"""
Django settings for appMercaSur project.

Generated by 'django-admin startproject' using Django 5.1.7.

For more information on this file, see
https://docs.djangoproject.com/en/5.1/topics/settings/

For the full list of settings and their values, see
https://docs.djangoproject.com/en/5.1/ref/settings/
"""

from pathlib import Path
import os
from celery import Celery
from dotenv import load_dotenv
from .jazzmin_settings import JAZZMIN_SETTINGS, JAZZMIN_UI_TWEAKS
load_dotenv()
# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent


# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/5.1/howto/deployment/checklist/

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = os.getenv('KEYDJANGO')
CODIGO_SECRETO_VALIDO = os.getenv('CODIGO_ACCESO_EMPRESA')

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = True

ALLOWED_HOSTS = ["notificaciones.mercasur.com.co","localhost","127.0.0.1","192.168.101.24"]
CSRF_TRUSTED_ORIGINS = ['https://notificaciones.mercasur.com.co:9180']
VUE_LOGIN_URL = 'https://notificaciones.mercasur.com.co:9180/inicio-sesion'

SERVERICG = os.getenv("SERVERICG")
DBICG = os.getenv("DATABASEICG")
USERICG = os.getenv("USERICG")
PASSICG = os.getenv("PASSWORDICG")
DRIVERICG = os.getenv("DRIVERICG")
PORTICG = os.getenv("PORTICG")

API_KEYRAPPI = os.getenv('API_KEY_RAPPI')
API_URLRAPPI = os.getenv('API_URL_RAPPI')
API_ENDPOINTRAPPI = os.getenv('API_ENDPOINT_RAPPI')
API_KEY_PARZE = os.getenv('API_KEYPARZE')
URL_PARZE = os.getenv('URl_PARZE')

ADMINS = [
    ('Nemesio Serrano', 'desarrollador@mercasur.com.co'),  # <- aquí los que quieren ver el error
]
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = 'smtp.gmail.com' # Servidor SMTP de tu proveedor
EMAIL_PORT = 587             # Puerto SMTP (587 para TLS, 465 para SSL)
EMAIL_USE_TLS = True         # Usar TLS (True para puerto 587)
EMAIL_CODIGO_COLABORADOR = os.getenv('CODIGO_COLABORADOR')


EMAIL_HOST_USER = os.getenv('DJANGO_EMAIL_USER')
EMAIL_HOST_PASSWORD = os.getenv('DJANGO_EMAIL_PASSWORD')

DEFAULT_FROM_EMAIL = EMAIL_HOST_USER
SERVER_EMAIL = DEFAULT_FROM_EMAIL

# Application definition

INSTALLED_APPS = [
    'jazzmin',
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.humanize',
    'django.contrib.sites',
    'whitenoise.runserver_nostatic',
    'django_celery_beat',
    'django_ckeditor_5',
    'auditlog',
    'simple_history',
    'automatizaciones.apps.AutomatizacionesConfig',
    'import_export',
    'clientes',
    'rest_framework',
    'corsheaders',
    'django_extensions',
    'presupuesto',
    'SoporteTI',
    'Compras',
]
SITE_ID = 1
SESSION_COOKIE_AGE = 2800
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
CORS_ALLOWED_ORIGINS = [
    "http://localhost:5173", 
    "http://127.0.0.1:5173",
    "https://fronted-mercasur.vercel.app",
    "http://181.204.212.122:9180",
    "http://notificaciones.mercasur.com.co",
    "https://notificaciones.mercasur.com.co:9180",
    "http://127.0.0.1:9000"
]

REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ),
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 1000,
    'DEFAULT_FILTER_BACKENDS': (
        'django_filters.rest_framework.DjangoFilterBackend',
        'rest_framework.filters.SearchFilter',
        'rest_framework.filters.OrderingFilter',
    ),
}


MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'auditlog.middleware.AuditlogMiddleware',
]

ROOT_URLCONF = 'appMercaSur.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

CKEDITOR_5_CONFIGS = {
    "default": {
        "toolbar": [
            "heading", "bold", "italic", "underline", "strikethrough",
            "bulletedList", "numberedList", "todoList",
            "blockQuote", "code", "codeBlock",
            "imageUpload", "mediaEmbed", "insertTable",
            "undo", "redo", "highlight", "fontSize", "fontColor",
            "mathType", "mention", "emoji"
        ],
        "heading": {
            "options": [
                {"model": "paragraph", "title": "Párrafo", "class": "ck-heading_paragraph"},
                {"model": "heading1", "view": "h1", "title": "Título 1", "class": "ck-heading_heading1"},
                {"model": "heading2", "view": "h2", "title": "Título 2", "class": "ck-heading_heading2"},
                {"model": "heading3", "view": "h3", "title": "Título 3", "class": "ck-heading_heading3"},
            ]
        },
        "codeBlock": {
            "languages": [
                {"language": "plaintext", "label": "Texto Plano"},
                {"language": "python", "label": "Python"},
                {"language": "javascript", "label": "JavaScript"},
                {"language": "html", "label": "HTML"},
            ]
        },
        "fontSize": {
            "options": ["tiny", "small", "default", "big", "huge"],
        },
        "fontColor": {
            "colors": [
                {"color": "hsl(0, 100%, 50%)", "label": "Rojo"},
                {"color": "hsl(120, 100%, 25%)", "label": "Verde"},
                {"color": "hsl(240, 100%, 50%)", "label": "Azul"},
            ],
        },
        "highlight": {
            "options": [
                {"model": "yellowMarker", "class": "marker-yellow", "title": "Resaltado amarillo"},
                {"model": "greenMarker", "class": "marker-green", "title": "Resaltado verde"},
            ]
        },
        "mathType": True,  # Activa MathType para ecuaciones
        "mention": {
            "feeds": [
                {"marker": "@", "feed": ["@admin", "@user1", "@user2"], "minimumCharacters": 1}
            ]
        },
        "emoji": True,  # Activa soporte para emojis
        "theme": "auto",  
        "language": "es",
    }
}
WSGI_APPLICATION = 'appMercaSur.wsgi.application'


# Database
# https://docs.djangoproject.com/en/5.1/ref/settings/#databases

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
       'NAME': os.getenv("NAME_DBP"),
        'USER': os.getenv("USER_DBP"),
        'PASSWORD': os.getenv("PASSWORD_DBP"),
        'HOST': os.getenv("HOST_DBP"),
        'PORT': os.getenv("PORT_DBP"),
    }
}


# Password validation
# https://docs.djangoproject.com/en/5.1/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]


# Internationalization
# https://docs.djangoproject.com/en/5.1/topics/i18n/

LANGUAGE_CODE = 'es-co'  # Español de Colombia

TIME_ZONE = 'America/Bogota'  # Zona horaria de Colombia

USE_I18N = True  # Habilitar la internacionalización

USE_L10N = True  # Formatear fechas y números según la localización

USE_TZ = True  # Habilitar soporte para zonas horarias


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/5.1/howto/static-files/
MEDIA_URL = '/media/'
MEDIA_ROOT = os.path.join(BASE_DIR, 'media')
print(MEDIA_URL, MEDIA_ROOT)

STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'


# Default primary key field type
# https://docs.djangoproject.com/en/5.1/ref/settings/#default-auto-field

CELERY_BROKER_URL = f"redis://127.0.0.1:{os.getenv('PORTREDIS')}/0"
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_BACKEND = f"redis://127.0.0.1:{os.getenv('PORTREDIS')}/0"

CELERY_BEAT_SCHEDULER = 'django_celery_beat.schedulers.DatabaseScheduler'

CKEDITOR_UPLOAD_PATH = "uploads/"
CKEDITOR_ALLOW_NONIMAGE_FILES = False

from kombu import Queue
CELERY_QUEUES = (
    Queue('cola_articulos',       routing_key='cola_articulos'),
    Queue('cola_articulos_total', routing_key='cola_articulos_total'),
    Queue('cola_parze',           routing_key='cola_parze'),
    Queue('cola_descuentos',      routing_key='cola_descuentos'),
    Queue('cola_correo',          routing_key='cola_correo'),
    Queue('codigo_temporal',      routing_key='codigo_temporal'),
)

CELERY_ROUTES = {
    'appMercaSur.tasks.procesar_articulos_task': {
        'queue': 'cola_articulos', 'routing_key': 'cola_articulos'
    },
    'appMercaSur.tasks.procesar_articulos_task_total': {
        'queue': 'cola_articulos_total', 'routing_key': 'cola_articulos_total'
    },
    'appMercaSur.tasks.procesar_articulos_parze_task': {
        'queue': 'cola_parze', 'routing_key': 'cola_parze'
    },
    'appMercaSur.tasks.actualizar_descuentos_task': {
        'queue': 'cola_descuentos', 'routing_key': 'cola_descuentos'
    },
    'automatizaciones.tasks.procesar_y_enviar_correo_task': {
        'queue': 'cola_correo', 'routing_key': 'cola_correo'
    },
     'clientes.tasks.generar_enviar_codigo_temporal':{
         'queue': 'codigo_temporal', 'routing_key': 'codigo_temporal'
    }
}