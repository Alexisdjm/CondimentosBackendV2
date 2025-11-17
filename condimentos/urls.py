from django.contrib import admin
from django.urls import path, include
from django.http import JsonResponse
from django.conf import settings
from django.conf.urls.static import static
from core.api.router import router
from core.api.views import CartApiViewSet

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

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/', include(router.urls)),

    # Acciones personalizadas del carrito
    path('api/cart-clear/', CartApiViewSet.as_view({'post': 'clear_cart'}), name='cart-clear'),
    path('api/sessions/list/', CartApiViewSet.as_view({'get': 'list_sessions'}), name='sessions-list'),
    path('api/sessions/clear-duplicates/', CartApiViewSet.as_view({'post': 'clear_duplicate_sessions'}), name='sessions-clear-duplicates'),
    path('api/sessions/clear-all/', CartApiViewSet.as_view({'post': 'clear_all_sessions'}), name='sessions-clear-all'),

    # Endpoint de debugging de sesiones
    path('api/debug-session/', CartApiViewSet.as_view({'get': 'debug_session'}), name='debug-session'),

    path('', api_root, name='home'),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
