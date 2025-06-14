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
    "user_menu": [
        {"name": "Perfil", "url": "/admin/auth/user/", "icon": "fas fa-user"},
        {"name": "Cerrar sesión", "url": "/admin/logout/", "icon": "fas fa-sign-out-alt"},
    ],
    "icons": {
        "auth.User": "fas fa-users",
        "auth.Group": "fas fa-users-cog",
        "clientes.Cliente": "fas fa-user-tie",
        "clientes.CodigoTemporal": "fas fa-key",
        "automatizaciones.Automatizacion": "fas fa-cogs",
        "SoporteTI.TicketSoporte": "fas fa-life-ring",
        "presupuesto.PresupuestoMensual": "fas fa-calendar-day",
        "presupuesto.PresupuestoDiarioCategoria": "fas fa-calendar-day",
        "presupuesto.VentaDiariaReal": "fas fa-money-bill-trend-up",
        "SoporteTI.Binnacle": "fas fa-book",
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
