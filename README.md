# MediCuida – Grupo 1

Prototipo académico no oficial de gestión de inventario ficticio de medicamentos. Incluye registro e inicio de sesión con DNI de prueba, dashboard y CRUD con SQLite.

## Ejecución local

Instala Python 3.9 o posterior y ejecuta `python backend/server.py`. Visita http://127.0.0.1:8765.

## Despliegue en Render

Servidor Python, plan Free, build command: `echo "Sin dependencias externas"`, start command: `python backend/server.py`. Configura `MEDICUIDA_HOST=0.0.0.0` y `MEDICUIDA_NO_BROWSER=1`. Render proporciona el puerto automáticamente.

**Advertencias:** solo datos ficticios, no afiliado al MINSA, no usar para tomar decisiones médicas, no ingresar DNI/correo reales. En Render Free, SQLite es temporal: los registros y usuarios se pierden después de un reinicio, suspensión o despliegue. Cualquier usuario registrado puede editar el inventario. No apto para producción.
