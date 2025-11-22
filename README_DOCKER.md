# Docker Deployment para Condimentos Backend

Este proyecto está configurado para deployment en Docker con soporte completo para el panel de administración de Django.

## Características

- ✅ Panel de administración accesible en `/admin`
- ✅ Servidor Gunicorn para producción
- ✅ WhiteNoise para servir archivos estáticos
- ✅ Configuración optimizada para HTTPS
- ✅ Migraciones automáticas al iniciar
- ✅ Recopilación automática de archivos estáticos

## Construcción de la Imagen

```bash
docker build -t condimentos-backend .
```

## Ejecución del Contenedor

### Desarrollo Local

```bash
docker-compose up
```

O manualmente:

```bash
docker run -d \
  -p 8000:8000 \
  -v $(pwd)/db.sqlite3:/app/db.sqlite3 \
  -v $(pwd)/static/images:/app/static/images \
  -e DEBUG=False \
  -e SECRET_KEY=tu-secret-key-segura \
  --name condimentos-backend \
  condimentos-backend
```

### Producción

Para producción, asegúrate de:

1. **Configurar variables de entorno:**

   ```bash
   export SECRET_KEY="tu-secret-key-muy-segura-aqui"
   export DEBUG="False"
   ```

2. **Construir la imagen:**

   ```bash
   docker build -t condimentos-backend .
   ```

3. **Ejecutar el contenedor:**
   ```bash
   docker run -d \
     -p 8000:8000 \
     -v /ruta/persistente/db.sqlite3:/app/db.sqlite3 \
     -v /ruta/persistente/static/images:/app/static/images \
     -e SECRET_KEY="${SECRET_KEY}" \
     -e DEBUG="False" \
     --name condimentos-backend \
     --restart unless-stopped \
     condimentos-backend
   ```

## Crear Superusuario para el Panel de Administración

Para acceder a `https://casacondimentos.com/admin`, necesitas crear un superusuario:

```bash
docker exec -it condimentos-backend python manage.py createsuperuser
```

Sigue las instrucciones para crear el usuario administrador.

## Acceso al Panel de Administración

Una vez desplegado, el panel de administración estará disponible en:

- **Producción:** `https://casacondimentos.com/admin`
- **Desarrollo local:** `http://localhost:8000/admin`

## Configuración del Servidor Web (Nginx/Apache)

Si usas un servidor web reverso (recomendado), configura el proxy para que apunte al contenedor:

### Ejemplo Nginx:

```nginx
server {
    listen 80;
    server_name casacondimentos.com www.casacondimentos.com;

    # Redirigir a HTTPS
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name casacondimentos.com www.casacondimentos.com;

    ssl_certificate /ruta/a/certificado.crt;
    ssl_certificate_key /ruta/a/private.key;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # Servir archivos estáticos directamente desde Nginx (opcional)
    location /static/ {
        alias /ruta/a/staticfiles/;
    }

    location /images/ {
        alias /ruta/a/static/images/;
    }
}
```

## Variables de Entorno

- `SECRET_KEY`: Clave secreta de Django (requerida en producción)
- `DEBUG`: Modo debug (`True` o `False`, por defecto `True`)

## Volúmenes Persistentes

Asegúrate de montar estos volúmenes para persistencia de datos:

- `db.sqlite3`: Base de datos
- `static/images`: Imágenes subidas
- `staticfiles`: Archivos estáticos recopilados

## Notas Importantes

1. **Seguridad:** Nunca uses la SECRET_KEY por defecto en producción. Genera una nueva con:

   ```python
   from django.core.management.utils import get_random_secret_key
   print(get_random_secret_key())
   ```

2. **Base de Datos:** El proyecto usa SQLite por defecto. Para producción con alto tráfico, considera usar PostgreSQL.

3. **Archivos Estáticos:** WhiteNoise sirve los archivos estáticos directamente desde Django. Para mejor rendimiento, considera usar un CDN o servirlos desde Nginx.

4. **HTTPS:** El proyecto está configurado para HTTPS. Asegúrate de tener certificados SSL válidos.
