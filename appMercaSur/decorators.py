from functools import wraps
from django.shortcuts import redirect
from django.contrib.auth import login
from django.conf import settings # Para importar VUE_LOGIN_URL
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework.exceptions import AuthenticationFailed

def jwt_login_required(view_func):
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        jwt_authenticator = JWTAuthentication()
        
        try:
            auth_result = jwt_authenticator.authenticate(request)
            
            if auth_result is None:
                raise AuthenticationFailed('No se proporcionó token de autenticación.')

            user, _ = auth_result
            
            if user and not request.user.is_authenticated:
                login(request, user)

        except AuthenticationFailed:
            login_url = 'http://localhost:5173/inicio-sesion'  
            return redirect(login_url) 
            
        return view_func(request, *args, **kwargs)

    return _wrapped_view