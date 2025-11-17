from rest_framework.routers import DefaultRouter
from .views import CartApiViewSet, QueryViewSet, ProductViewSet, CategoryViewSet

router = DefaultRouter()

# Registrar ViewSets disponibles
router.register(prefix=r'consulta', basename='consulta', viewset=QueryViewSet)
router.register(prefix=r'cart', basename='cart', viewset=CartApiViewSet)

# URLs para productos (PDP y Homepage)
router.register(prefix=r'item', basename='item', viewset=ProductViewSet)
router.register(prefix=r'products', basename='products', viewset=ProductViewSet)
router.register(prefix=r'category', basename='category', viewset=CategoryViewSet)
