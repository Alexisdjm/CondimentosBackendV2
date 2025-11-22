#!/bin/bash
set -e

echo "Ejecutando migraciones..."
python manage.py migrate --noinput

echo "Recopilando archivos estáticos..."
python manage.py collectstatic --noinput

echo "Verificando si existe un superusuario..."
python manage.py shell << EOF
from django.contrib.auth import get_user_model
User = get_user_model()
if not User.objects.filter(is_superuser=True).exists():
    print("No se encontró un superusuario. Por favor, créalo manualmente con:")
    print("python manage.py createsuperuser")
else:
    print("Superusuario encontrado.")
EOF

echo "Iniciando servidor..."
exec "$@"
