from functools import wraps
from django.shortcuts import redirect
from django.contrib.auth import login
from django.conf import settings
from django.http import HttpResponseServerError # Para errores inesperados graves
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework.exceptions import AuthenticationFailed
import logging

logger = logging.getLogger(__name__)

def smart_jwt_login_required(view_func):
    """
    Decorador simplificado:
    1. Si hay sesión de Django, permite acceso.
    2. Si no, intenta autenticar con JWT y crear sesión.
    3. Si falla JWT, redirige al login de Vue.
    """
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        # --- PASO 1: VERIFICAR SESIÓN DE DJANGO EXISTENTE ---
        if request.user.is_authenticated:
            logger.debug(f"Usuario '{request.user}' ya autenticado por sesión. Accediendo a la vista.")
            return view_func(request, *args, **kwargs)

        # --- PASO 2: INTENTAR AUTENTICACIÓN POR JWT Y CREAR SESIÓN ---
        jwt_authenticator = JWTAuthentication()
        user_from_jwt = None
        
        try:
            logger.debug("No hay sesión de Django. Intentando autenticación JWT...")
            # El método authenticate() puede devolver (user, token) o None si no hay token.
            # También puede lanzar AuthenticationFailed si el token es inválido/expirado.
            auth_result = jwt_authenticator.authenticate(request) 
            
            if auth_result:
                user_from_jwt, _ = auth_result
                if user_from_jwt:
                    if not user_from_jwt.is_active:
                        logger.warning(f"Intento de login JWT para usuario inactivo: {user_from_jwt}")
                        raise AuthenticationFailed('Cuenta de usuario inactiva.') # Será capturado abajo
                    
                    # Usuario del token es válido y activo, crear sesión de Django
                    logger.debug(f"Usuario JWT '{user_from_jwt}' es válido y activo. Intentando login().")
                    login(request, user_from_jwt, backend='django.contrib.auth.backends.ModelBackend')
                    logger.info(f"Sesión de Django creada para '{user_from_jwt}' vía JWT.")
                    # Ahora request.user está actualizado con el usuario de la sesión recién creada.
                    # Continuamos para ejecutar la vista original.
                    return view_func(request, *args, **kwargs)
                else:
                    # Caso improbable: auth_result no es None, pero user_from_jwt sí lo es.
                    logger.warning("Autenticación JWT devolvió un resultado pero sin objeto de usuario.")
                    # Se tratará como un fallo de autenticación general abajo.
            else:
                # auth_result es None, significa que no se encontró un token en el encabezado.
                logger.info("No se encontró token JWT en el encabezado. Redirigiendo al login.")
                login_url = getattr(settings, 'VUE_LOGIN_URL', '/')
                return redirect(login_url)

        except AuthenticationFailed as e:
            # El token es inválido, ha expirado, o el usuario está inactivo.
            logger.warning(f"Fallo en autenticación JWT (AuthenticationFailed): {e}. Redirigiendo al login.")
            login_url = getattr(settings, 'VUE_LOGIN_URL', '/')
            return redirect(login_url)
        except Exception as e:
            # Cualquier otro error inesperado durante el proceso JWT o login().
            logger.error(f"Error inesperado durante autenticación JWT o login(): {e}", exc_info=True)
            # En lugar de redirigir, un error 500 podría ser más apropiado aquí para depurar
            # ya que es una falla inesperada del servidor.
            return HttpResponseServerError("Error interno del servidor durante el proceso de autenticación.")
            
        # Failsafe: Si por alguna razón no se autenticó ni se redirigió, redirigir.
        # Este bloque no debería alcanzarse si la lógica anterior es correcta.
        logger.error("Failsafe: El flujo del decorador llegó a un punto inesperado sin autenticación. Redirigiendo al login.")
        login_url = getattr(settings, 'VUE_LOGIN_URL', '/')
        return redirect(login_url)

    return _wrapped_view
