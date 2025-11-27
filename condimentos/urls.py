from django.contrib import admin
from django.urls import path, include, re_path
from django.http import JsonResponse, FileResponse, Http404
from django.conf import settings
from django.conf.urls.static import static
from django.views.static import serve
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import ensure_csrf_cookie
from django.middleware.csrf import get_token
from core.api.router import router
from core.api.views import CartApiViewSet
import os

def api_root(request):
    # """Vista raíz que muestra información sobre la API"""
    return JsonResponse({
        'message': 'Bienvenido a la API de Condimentos',
        'version': '1.0',
        'endpoints': {
            'api': '/api/',
            'admin': '/admin/',
        },
        'documentation': 'Accede a /api/ para ver todos los endpoints disponibles',
        'frontend': 'Esta API está diseñada para ser consumida por una aplicación React separada'
    })

def serve_media(request, path):
    """
    Vista personalizada para servir archivos media en producción.
    Funciona tanto en desarrollo (DEBUG=True) como en producción (DEBUG=False).
    """
    file_path = os.path.join(settings.MEDIA_ROOT, path)
    if os.path.exists(file_path) and os.path.isfile(file_path):
        # Determinar el tipo MIME basado en la extensión del archivo
        ext = os.path.splitext(file_path)[1].lower()
        mime_types = {
            '.jpg': 'image/jpeg',
            '.jpeg': 'image/jpeg',
            '.png': 'image/png',
            '.gif': 'image/gif',
            '.webp': 'image/webp',
            '.svg': 'image/svg+xml',
        }
        content_type = mime_types.get(ext, 'application/octet-stream')
        return FileResponse(open(file_path, 'rb'), content_type=content_type)
    raise Http404("Archivo no encontrado")

@require_http_methods(["GET"])
@ensure_csrf_cookie
def get_csrf_token(request):
    """
    Endpoint para obtener el token CSRF.
    Establece la cookie CSRF y devuelve el token en la respuesta JSON.
    El frontend debe llamar a este endpoint antes de hacer requests POST/PUT/DELETE.
    """
    token = get_token(request)
    return JsonResponse({'csrfToken': token})

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/', include(router.urls)),

    # Endpoint para obtener el token CSRF
    path('api/csrf-token/', get_csrf_token, name='csrf-token'),

    # Acciones personalizadas del carrito
    path('api/cart-clear/', CartApiViewSet.as_view({'post': 'clear_cart'}), name='cart-clear'),
    path('api/sessions/list/', CartApiViewSet.as_view({'get': 'list_sessions'}), name='sessions-list'),
    path('api/sessions/clear-duplicates/', CartApiViewSet.as_view({'post': 'clear_duplicate_sessions'}), name='sessions-clear-duplicates'),
    path('api/sessions/clear-all/', CartApiViewSet.as_view({'post': 'clear_all_sessions'}), name='sessions-clear-all'),

    # Endpoint de debugging de sesiones
    path('api/debug-session/', CartApiViewSet.as_view({'get': 'debug_session'}), name='debug-session'),

    # Servir archivos media (imágenes)
    re_path(r'^images/(?P<path>.*)$', serve_media, name='serve_media'),

    path('', api_root, name='home'),
]

# Solo agregar static() en desarrollo (DEBUG=True)
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
