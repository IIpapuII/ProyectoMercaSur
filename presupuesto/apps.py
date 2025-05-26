from django.apps import AppConfig


class PresupuestoConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'presupuesto'
    verbose_name = "Presupuesto y Ventas"

    def ready(self):
        print("PresupuestoConfig is ready")
        import presupuesto.signals
        