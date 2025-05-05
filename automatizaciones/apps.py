# automatizaciones/apps.py
from django.apps import AppConfig

class AutomatizacionesConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'automatizaciones' 

    def ready(self):
        """
        Este método se ejecuta cuando Django está listo.
        Importamos las señales aquí para registrarlas.
        """
        print(f"App '{self.name}' lista. Registrando señales...") 
        try:
            import automatizaciones.signals
            print(f"Señales de '{self.name}' importadas correctamente.") 
        except ImportError:
            print(f"Advertencia: No se pudo importar '{self.name}.signals'. Asegúrate que el archivo exista.")

