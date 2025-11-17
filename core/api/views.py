from rest_framework import viewsets, status
from rest_framework.response import Response
from rest_framework.decorators import action
from django.contrib.sessions.models import Session
from django.utils import timezone
from core.models import Product
from .serializers import ProductSerializer
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.db.models import Count
import threading

# Lock para prevenir múltiples sesiones simultáneas
session_lock = threading.Lock()

class CartApiViewSet(viewsets.ModelViewSet):
    """
    ViewSet para manejar el carrito de compras usando sesiones de Django.
    """
    queryset = Product.objects.all()
    serializer_class = ProductSerializer

    def _ensure_session(self, request):
        """
        Asegura que existe una sesión válida.
        """
        with session_lock:
            if not request.session.session_key:
                has_cart_data = request.data.get('cart') or request.data.get('product_id')
                has_cart_in_session = request.session.get('cart', {})

                if has_cart_data or has_cart_in_session:
                    request.session.create()
                else:
                    pass
            else:
                pass

        return request.session

    def _get_cart(self, request):
        """
        Obtiene el carrito de la sesión actual.
        """
        cart = request.session.get('cart', {})
        if not isinstance(cart, dict):
            return {}
        return cart

    def _save_cart(self, request, cart):
        """
        Guarda el carrito en la sesión.
        """
        request.session['cart'] = cart
        request.session.modified = True
        request.session.save()

    def _convert_to_grams(self, cantidad, measurement, display_value=None):
        """
        Convierte la cantidad recibida a gramos para manejo interno.
        """
        measurement = (measurement or "").lower()

        def _safe_float(value, default=0.0):
            try:
                if value is None:
                    return default
                return float(value)
            except (TypeError, ValueError):
                return default

        cantidad = _safe_float(cantidad)
        display_value = _safe_float(display_value, default=None)

        if measurement == 'kg':
            value = display_value if display_value is not None else cantidad
            return value * 1000
        if measurement == 'gm':
            return display_value if display_value is not None else cantidad
        # Para otras medidas (incluyendo ambas 'bo'), asumimos gramos si display_value está presente
        if display_value is not None:
            return display_value
        return cantidad

    def _extract_existing_weight(self, item):
        """
        Obtiene la cantidad en gramos almacenada previamente.
        """
        if not item:
            return 0

        if 'cantidad_total_gramos' in item:
            try:
                return float(item['cantidad_total_gramos'])
            except (TypeError, ValueError):
                return 0

        medida = (item.get('medida') or '').lower()
        cantidad = item.get('cantidad', 0)
        try:
            cantidad = float(cantidad)
        except (TypeError, ValueError):
            cantidad = 0

        if medida == 'kg':
            return cantidad * 1000
        if medida == 'gm':
            return cantidad
        return 0

    def _format_weight(self, grams):
        """
        Devuelve una representación legible (kg/g) para la cantidad en gramos.
        """
        grams = int(round(float(grams)))
        kilos, remainder = divmod(grams, 1000)
        parts = []
        if kilos:
            parts.append(f"{kilos}kg")
        if remainder:
            parts.append(f"{remainder}g")
        if not parts:
            parts.append("0g")
        return " ".join(parts)

    def _extract_existing_units(self, item):
        if not item:
            return 0
        try:
            return int(item.get('cantidad', 0))
        except (TypeError, ValueError):
            return 0

    def list(self, request, *args, **kwargs):
        """
        Obtener el contenido actual del carrito.
        Retorna todos los productos en el carrito con información de sesión.
        """
        try:
            # Obtener el carrito de la sesión actual
            cart = self._get_cart(request)
            session = request.session

            # Calcular total_items considerando productos por unidad
            # Para productos por unidad, total_items debe reflejar el número de unidades agregadas
            # Para productos por peso, total_items es el número de productos únicos
            total_items = 0
            for item in cart.values():
                if not isinstance(item, dict):
                    continue
                if item.get('medida') == 'un' or item.get('cantidad_total_unidades'):
                    # Producto por unidad: contar las unidades
                    unidades = self._extract_existing_units(item)
                    total_items += unidades
                else:
                    # Producto por peso: contar como 1 producto único
                    total_items += 1

            transformed_cart = {}
            for key, item in cart.items():
                if not isinstance(item, dict):
                    continue
                transformed = dict(item)

                if 'cantidad_total_gramos' in item:
                    try:
                        grams = float(item['cantidad_total_gramos'])
                        transformed['cantidad_total_gramos'] = grams
                        transformed['cantidad_formateada'] = self._format_weight(grams)
                    except (TypeError, ValueError):
                        pass

                transformed_cart[key] = transformed

            return Response({
                'cart': transformed_cart,
                'session_key': request.session.session_key,
                'total_items': total_items,
                'item_count': total_items,  # Agregar item_count para compatibilidad con frontend
                'session_expires': session.get_expiry_date().isoformat() if session.get_expiry_date() else None
            })

        except Exception as e:
            return Response(
                {"detail": f"Error al obtener el carrito: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    def create(self, request, *args, **kwargs):
        """
        Agregar un producto al carrito.
        """
        try:

            product_id = request.data.get('product_id')
            cantidad = request.data.get('cantidad', 1)
            measurement = request.data.get('measurement', 'un')
            display_value = request.data.get('display_value')

            if not product_id:
                return Response(
                    {"detail": "product_id es requerido."},
                    status=status.HTTP_400_BAD_REQUEST
                )

            try:
                product = Product.objects.get(id=product_id)
            except Product.DoesNotExist:
                return Response(
                    {"detail": "Producto no encontrado."},
                    status=status.HTTP_404_NOT_FOUND
                )

            # Asegurar que existe una sesión
            self._ensure_session(request)

            # Obtener el carrito actual
            cart = self._get_cart(request)
            cart_key = str(product_id)
            existing_item = cart.get(cart_key)

            measurement = (measurement or "").lower()


            # Agregar o actualizar el producto en el carrito
            cart_total_grams = 0
            cart_total_units = 0

            cart_entry = {
                'id': product.id,
                'name': product.name,
                'description': product.description,
                'image': product.image.url if product.image else None,
                'added_at': timezone.now().isoformat(),
                'last_measurement': measurement,
            }

            if measurement == 'un' or product.measurement == 'un':
                unidades_actuales = self._extract_existing_units(existing_item)
                try:
                    unidades_a_agregar = int(cantidad)
                except (TypeError, ValueError):
                    unidades_a_agregar = 0
                total_unidades = unidades_actuales + unidades_a_agregar
                cart_total_units = total_unidades
                cart_entry.update(
                    {
                        'cantidad': total_unidades,
                        'medida': 'un',
                        'cantidad_total_unidades': total_unidades,
                        'cantidad_formateada': f"{total_unidades} unidades",
                    }
                )
            else:
                gramos_a_agregar = self._convert_to_grams(
                    cantidad, measurement, display_value
                )
                gramos_existentes = self._extract_existing_weight(existing_item)
                total_gramos = gramos_existentes + gramos_a_agregar
                cart_entry.update(
                    {
                        'cantidad': total_gramos,
                        'medida': 'gm',
                        'cantidad_total_gramos': total_gramos,
                        'cantidad_formateada': self._format_weight(total_gramos),
                        'cantidad_detalle': {
                            'kg': int(total_gramos // 1000),
                            'gm': int(total_gramos % 1000),
                        },
                    }
                )
                cart_total_grams = total_gramos

            cart[cart_key] = cart_entry

            # Guardar el carrito en la sesión
            self._save_cart(request, cart)

            # Calcular total_items considerando productos por unidad
            # Para productos por unidad, total_items debe reflejar el número de unidades agregadas
            # Para productos por peso, total_items es el número de productos únicos
            total_items = 0
            for item in cart.values():
                if item.get('medida') == 'un' or item.get('cantidad_total_unidades'):
                    # Producto por unidad: contar las unidades
                    unidades = self._extract_existing_units(item)
                    total_items += unidades
                else:
                    # Producto por peso: contar como 1 producto único
                    total_items += 1

            total_units = sum(
                self._extract_existing_units(item) for item in cart.values()
            )
            total_grams = sum(
                self._extract_existing_weight(item) for item in cart.values()
            )

            return Response({
                'cart': cart,
                'message': f'Producto "{product.name}" agregado al carrito',
                'added_product': cart[cart_key],
                'session_key': request.session.session_key,
                'item_count': total_items,  # Agregar item_count para compatibilidad con frontend
                'summary': {
                    'total_items': total_items,
                    'total_units': total_units,
                    'total_grams': total_grams,
                    'cart_total_units': cart_total_units,
                    'cart_total_grams': cart_total_grams,
                },
            })

        except Product.DoesNotExist:
            return Response(
                {"detail": "Producto no encontrado."},
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            return Response(
                {"detail": f"Error al agregar al carrito: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    def update(self, request, *args, **kwargs):
        """
        Actualizar la cantidad de un producto en el carrito.
        """
        try:
            product_id = str(kwargs.get('pk'))
            new_cantidad = request.data.get('cantidad', 1)

            if not product_id:
                return Response(
                    {"detail": "ID del producto es requerido."},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # Obtener el carrito actual
            cart = self._get_cart(request)

            if product_id not in cart:
                return Response(
                    {"detail": "Producto no encontrado en el carrito."},
                    status=status.HTTP_404_NOT_FOUND
                )

            # Actualizar la cantidad
            cart[product_id]['cantidad'] = new_cantidad

            # Guardar el carrito en la sesión
            self._save_cart(request, cart)

            return Response({
                'cart': cart,
                'message': f'Cantidad actualizada para tipo de producto {product_id}',
                'updated_product': cart[product_id],
                'session_key': request.session.session_key
            })

        except Exception as e:
            return Response(
                {"detail": f"Error al actualizar el carrito: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    def destroy(self, request, *args, **kwargs):
        """
        Eliminar un producto del carrito.
        """
        try:
            product_id = str(kwargs.get('pk'))

            if not product_id:
                return Response(
                    {"detail": "ID del producto es requerido."},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # Obtener el carrito actual
            cart = self._get_cart(request)

            if product_id not in cart:
                return Response(
                    {"detail": "Producto no encontrado en el carrito."},
                    status=status.HTTP_404_NOT_FOUND
                )

            # Eliminar el producto del carrito
            removed_product = cart.pop(product_id)

            # Guardar el carrito en la sesión
            self._save_cart(request, cart)

            # Calcular total_items considerando productos por unidad
            total_items = 0
            for item in cart.values():
                if not isinstance(item, dict):
                    continue
                if item.get('medida') == 'un' or item.get('cantidad_total_unidades'):
                    # Producto por unidad: contar las unidades
                    unidades = self._extract_existing_units(item)
                    total_items += unidades
                else:
                    # Producto por peso: contar como 1 producto único
                    total_items += 1

            return Response({
                'cart': cart,
                'message': f'Producto "{removed_product["name"]}" eliminado del carrito',
                'removed_product': removed_product,
                'session_key': request.session.session_key,
                'item_count': total_items,
                'total_items': total_items,
            })

        except Exception as e:
            return Response(
                {"detail": f"Error al eliminar del carrito: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @action(detail=False, methods=['post'])
    def clear_cart(self, request):
        """
        Limpiar todo el carrito.
        """
        try:
            # Limpiar el carrito de la sesión
            request.session['cart'] = {}
            request.session.modified = True
            request.session.save()

            return Response({
                'cart': {},
                'message': 'Carrito limpiado.',
                'session_key': request.session.session_key
            })

        except Exception as e:
            return Response(
                {"detail": f"Error al limpiar el carrito: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @action(detail=False, methods=['get'])
    def list_sessions(self, request):
        """
        Listar todas las sesiones activas.
        """
        try:
            sessions = Session.objects.all()
            session_info = []

            for session in sessions:
                session_data = session.get_decoded()
                session_info.append({
                    'session_key': session.session_key,
                    'expire_date': session.expire_date.isoformat() if session.expire_date else None,
                    'has_cart': 'cart' in session_data,
                    'cart_items': len(session_data.get('cart', {})),
                    'is_expired': session.expire_date <= timezone.now() if session.expire_date else False
                })

            return Response({
                'sessions': session_info,
                'total_sessions': len(session_info),
                'active_sessions': len([s for s in session_info if not s['is_expired']])
            })

        except Exception as e:
            return Response(
                {"detail": f"Error al listar sesiones: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @action(detail=False, methods=['post'])
    def clear_duplicate_sessions(self, request):
        """
        Limpiar sesiones duplicadas.
        """
        try:
            sessions = Session.objects.all()
            duplicate_count = 0

            for session in sessions:
                if session.expire_date <= timezone.now():
                    session.delete()
                    duplicate_count += 1

            return Response({
                'message': f'Se eliminaron {duplicate_count} sesiones duplicadas',
                'deleted_sessions': duplicate_count
            })

        except Exception as e:
            return Response(
                {"detail": f"Error al limpiar sesiones duplicadas: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @action(detail=False, methods=['post'])
    def clear_all_sessions(self, request):
        """
        Limpiar todas las sesiones.
        """
        try:
            sessions = Session.objects.all()
            total_count = len(sessions)

            for session in sessions:
                session.delete()

            return Response({
                'message': f'Se eliminaron {total_count} sesiones',
                'deleted_sessions': total_count
            })

        except Exception as e:
            return Response(
                {"detail": f"Error al limpiar todas las sesiones: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

class QueryViewSet(viewsets.ModelViewSet):
    """
    ViewSet para búsqueda de productos con paginación.
    """
    queryset = Product.objects.all()
    serializer_class = ProductSerializer

    def list(self, request, *args, **kwargs):
        """
        Obtener todos los productos con paginación.
        Endpoint: /api/consulta/?page=1
        """
        try:
            cookies = request.COOKIES
            print(f"[DEBUG] Cookies recibidas: {cookies}")

            if not request.session.session_key:
                request.session.create()
                request.session["initialized"] = True
                request.session.modified = True

            # Obtener parámetros de paginación
            page = int(request.query_params.get('page', 1))
            page_size = int(request.query_params.get('page_size', 12))  # 12 productos por página por defecto

            # Calcular offset
            offset = (page - 1) * page_size

            # Obtener productos con paginación
            products = Product.objects.all()[offset:offset + page_size]
            total_products = Product.objects.count()

            # Calcular información de paginación
            total_pages = (total_products + page_size - 1) // page_size
            has_next = page < total_pages
            has_previous = page > 1

            serializer = self.get_serializer(products, many=True)
            return Response({
                'products': serializer.data,
                'pagination': {
                    'current_page': page,
                    'page_size': page_size,
                    'total_products': total_products,
                    'total_pages': total_pages,
                    'has_next': has_next,
                    'has_previous': has_previous,
                    'next_page': page + 1 if has_next else None,
                    'previous_page': page - 1 if has_previous else None
                }
            })
        except ValueError as e:
            return Response(
                {"detail": f"Parámetros de paginación inválidos: {str(e)}"},
                status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            return Response(
                {"detail": f"Error al obtener productos: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @action(detail=False, methods=['get'])
    def search(self, request):
        """
        Buscar productos por nombre o descripción.
        """
        try:
            query = (request.query_params.get('q', '') or '').strip()

            # Validar longitud mínima de la consulta
            if len(query) < 2:
                return Response(
                    {
                        "detail": "Debes escribir al menos 2 caracteres para realizar una búsqueda.",
                        "products": [],
                        "total": 0,
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # Filtrar por nombre o descripción que contengan el texto
            products = Product.objects.filter(
                name__icontains=query
            ) | Product.objects.filter(
                description__icontains=query
            )

            serializer = self.get_serializer(products, many=True)

            return Response(
                {
                    "products": serializer.data,
                    "total": products.count(),
                    "query": query,
                }
            )
        except Exception as e:
            return Response(
                {"detail": f"Error en la búsqueda: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class ProductViewSet(viewsets.ModelViewSet):
    """
    ViewSet para manejar productos individuales.
    Endpoints: /api/item/{id}/ y /api/products/{id}/
    """
    queryset = Product.objects.all()
    serializer_class = ProductSerializer


    def retrieve(self, request, *args, **kwargs):
        """
        Obtener un producto específico por ID.
        Endpoint: /api/item/{id}/
        """
        try:
            product = self.get_object()
            serializer = self.get_serializer(product)
            return Response({
                'product': serializer.data
            })
        except Product.DoesNotExist:
            return Response(
                {"detail": "Producto no encontrado."},
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            return Response(
                {"detail": f"Error al obtener producto: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @action(detail=False, methods=['get'])
    def featured(self, request):
        """
        Obtener productos destacados.
        Endpoint: /api/products/featured/
        """
        try:
            # Por ahora retorna todos los productos, puedes agregar lógica para destacados
            featured_products = Product.objects.all()[:6]  # Primeros 6 productos
            serializer = self.get_serializer(featured_products, many=True)
            return Response({
                'featured_products': serializer.data,
                'total': featured_products.count()
            })
        except Exception as e:
            return Response(
                {"detail": f"Error al obtener productos destacados: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @action(detail=False, methods=['get'])
    def by_category(self, request, category=None):
        """
        Obtener productos por categoría.
        Endpoint: /api/products/{category}/
        """
        try:
            if category:
                products = Product.objects.filter(category__iexact=category)
            else:
                products = Product.objects.all()

            serializer = self.get_serializer(products, many=True)
            return Response({
                'products': serializer.data,
                'category': category,
                'total': products.count()
            })
        except Exception as e:
            return Response(
                {"detail": f"Error al obtener productos por categoría: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class CategoryViewSet(viewsets.ViewSet):
    """
    ViewSet para obtener productos filtrados por código de categoría.
    Endpoint: /api/category/{code}/  (p. ej. /api/category/co/)
    """
    serializer_class = ProductSerializer

    def list(self, request):
        """
        Devolver todas las categorías disponibles basadas en los choices del modelo,
        indicando cuáles tienen productos actualmente.
        """
        category_choices = dict(Product._meta.get_field("category").choices)
        products_by_category = (
            Product.objects.values("category")
            .order_by("category")
            .annotate(count=Count("id"))
        )

        counts_map = {item["category"]: item["count"] for item in products_by_category}

        categories = [
            {
                "code": code,
                "name": category_choices.get(code, code),
                "product_count": counts_map.get(code, 0),
            }
            for code in category_choices.keys()
        ]

        return Response(
            {
                "categories": categories,
                "total": len(categories),
            }
        )

    def retrieve(self, request, pk=None):
        """
        Obtener productos por código de categoría (dos caracteres) con paginación opcional.
        """
        if not pk:
            return Response(
                {"detail": "Debes proporcionar un código de categoría."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        code = pk.lower()
        products_qs = Product.objects.filter(category__iexact=code).order_by("id")
        total_products = products_qs.count()

        page = request.query_params.get("page", 1)
        page_size = request.query_params.get("page_size", 12)

        try:
            page = int(page)
            page_size = int(page_size)
            if page < 1 or page_size < 1:
                raise ValueError
        except (ValueError, TypeError):
            return Response(
                {"detail": "Parámetros de paginación inválidos."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        paginator = Paginator(products_qs, page_size)

        try:
            products_page = paginator.page(page)
        except PageNotAnInteger:
            products_page = paginator.page(1)
            page = 1
        except EmptyPage:
            products_page = paginator.page(paginator.num_pages)
            page = paginator.num_pages

        serializer = ProductSerializer(
            products_page.object_list, many=True, context={"request": request}
        )

        return Response(
            {
                "category": code,
                "products": serializer.data,
                "pagination": {
                    "current_page": page,
                    "page_size": page_size,
                    "total_products": total_products,
                    "total_pages": paginator.num_pages,
                    "has_next": products_page.has_next(),
                    "has_previous": products_page.has_previous(),
                    "next_page": products_page.next_page_number()
                    if products_page.has_next()
                    else None,
                    "previous_page": products_page.previous_page_number()
                    if products_page.has_previous()
                    else None,
                },
            }
        )
