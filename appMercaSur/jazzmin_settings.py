JAZZMIN_SETTINGS = {
    "site_title": "Panel de Administración",
    "site_header": "mercasur",
    "site_logo": "images/logo.png",  # Ruta dentro de STATIC
    "login_logo": "images/logo.png",
    "site_icon": "images/favicon.ico",  # Favicon
    "welcome_sign": "Bienvenido al Panel de Administración",
    "user_avatar":None,
    "show_ui_builder": True,
    "navigation_expanded": False,
    "topmenu_links": [
        {"name": "Inicio", "url": "/admin/", "icon": "fas fa-home", "new_window": False},
    ],
    "usermenu_links": [
        {"name": "Documentación", "url": "https://docs.mercasur.com", "icon": "fas fa-book", "new_window": True},
    ],
    
    "icons": {
        "auth.User": "fas fa-users",
        "auth.Group": "fas fa-users-cog",
        "presupuesto.PresupuestoMensual": "fas fa-calendar-day",
        "presupuesto.PresupuestoDiarioCategoria": "fas fa-calendar-day",
        "presupuesto.VentaDiariaReal": "fas fa-money-bill-trend-up",
        "SoporteTI.Binnacle": "fas fa-book",
        "automatizaciones.ApiLogRappi": "fas fa-file-alt",
        "automatizaciones.Articulos": "fas fa-box",
        "automatizaciones.CorreoEnviado": "fas fa-cogs",
        "automatizaciones.DescuentoDiario": "fas fa-percent",
        "automatizaciones.EnvioLog": "fas fa-clipboard-list",
        "automatizaciones.ProductSku": "fas fa-barcode",
        "automatizaciones.Product": "fas fa-boxes",
        "automatizaciones.SQLQuery": "fas fa-database",
        "clientes.barrio": "fas fa-map-marked-alt",                     
        "clientes.CodigoTemporal": "fas fa-key",                       
        "clientes.RegistroCliente": "fas fa-address-book",            
        "clientes.SecuenciaCodCliente": "fas fa-list-ol",         
        "clientes.ZonaPermitida": "fas fa-map-pin",
        "presupuesto.Sede": "fas fa-building",
        "presupuesto.PorcentajeDiarioConfig": "fas fa-percentage",
        "presupuesto.CategoriaVenta": "fas fa-tags",
        "presupuesto.Eventos": "fas fa-calendar-alt",
        "presupuesto.PresupuestoMensualCategoria": "fas fa-calendar-week",
        "presupuesto.PresupuestoDiarioCategoria": "fas fa-calendar-day",
        "presupuesto.ventapollos": "fas fa-drumstick-bite",
        "SoporteTI.TicketSoporte": "fas fa-life-ring",
        "SoporteTI.Department": "fas fa-building",
        "SoporteTI.EquipmentCategory": "fas fa-desktop",
        "SoporteTI.Employee": "fas fa-user-tie",
        "SoporteTI.Location": "fas fa-map-marker-alt",
        "SoporteTI.Equipment": "fas fa-laptop",
        "SoporteTI.CategoryOfIncidence": "fas fa-exclamation-triangle",
        "SoporteTI.Binnacle": "fas fa-book",
        "SoporteTI.BinnacleDasboardProxy": "fas fa-tachometer-alt",
        "celery.PeriodicTask": "fas fa-clock",
        "celery.IntervalSchedule": "fas fa-stopwatch",
        "celery.CrontabSchedule": "fas fa-calendar-alt",
        "celery.ClockedSchedule": "fas fa-clock",
        "django_celery_beat.PeriodicTask": "fas fa-clock",
        "django_celery_beat.IntervalSchedule": "fas fa-stopwatch",
        "django_celery_beat.CrontabSchedule": "fas fa-calendar-alt",
        "django_celery_beat.ClockedSchedule": "fas fa-clock",
        "auditlog.logentry": "fas fa-history",
        # Íconos de las apps (carpetas principales del menú)
        "admin": "fas fa-th-large",               # Panel de control
        "auditlog": "fas fa-clipboard-check",     # Audit log
        "auth": "fas fa-user-shield",             # Autenticación y autorización
        "automatizaciones": "fas fa-robot",       # Automatizaciones
        "clientes": "fas fa-users",               # Clientes
        "presupuesto": "fas fa-chart-line",            # Presupuesto y Ventas
        "SoporteTi": "fas fa-tools",                # Soporte TI
        "django_celery_beat": "fas fa-sync-alt",              # Tareas Periódica
    },
    "related_modal_active": True,
    "default_icon_parents": "fas fa-folder",
    "default_icon_children": "fas fa-file",
    "changeform_format": "horizontal_tabs",
    "changeform_format_overrides": {
        "auth.User": "horizontal_tabs",
        "clientes.Cliente": "collapsible",
        "presupuesto.PresupuestoMensual": "collapsible",
        "presupuesto.PresupuestoDiarioCategoria": "collapsible",
        "presupuesto.VentaDiariaReal": "collapsible",
        "SoporteTI.Binnacle": "collapsible",
    },
    "custom_css": "images/custom.css",  # Ruta dentro de STATIC
    "related_modal_active": False,
    "custom_links": {
        "SoporteTI.Binnacle": [
            {
                "name": "Dashboard Bitácora 202 admin",
                "url": "binnacle_dashboard_admin",
                "icon": "fas fa-chart-pie",
            },
    ],
},
}

JAZZMIN_UI_TWEAKS = {
    "navbar_small_text": False,
    "footer_small_text": False,
    "body_small_text": True,
    "brand_small_text": False,
    "brand_colour": "navbar-white",
    "accent": "accent-success",
    "navbar": "navbar-success navbar-dark",
    "no_navbar_border": False,
    "navbar_fixed": True,
    "layout_boxed": False,
    "footer_fixed": False,
    "sidebar_fixed": False,
    "sidebar": "sidebar-light-danger",
    "sidebar_nav_small_text": False,
    "sidebar_disable_expand": False,
    "sidebar_nav_child_indent": False,
    "sidebar_nav_compact_style": False,
    "sidebar_nav_legacy_style": False,
    "sidebar_nav_flat_style": False,
    "theme": "default",
    "dark_mode_theme": None,
    "button_classes": {
        "primary": "btn-outline-primary",
        "secondary": "btn-outline-secondary",
        "info": "btn-info",
        "warning": "btn-warning",
        "danger": "btn-danger",
        "success": "btn-success"
    },
    "actions_sticky_top": False
}
