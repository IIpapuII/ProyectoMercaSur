from django.apps import AppConfig


class ComprasConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'Compras'
    
    def ready(self):
        # Importar signals para registrarlos
        import Compras.signals
