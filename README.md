# MediCuida – Grupo 1

**Prototipo académico no oficial.** Sistema demostrativo de gestión inclusiva de medicamentos. No está afiliado al MINSA, no valida identidades profesionales ni consentimientos médicos. Usar únicamente DNIs y medicamentos ficticios.

## Funcionalidades

- Registro con **Paciente**, **Cuidador** o **Médico**, y campos específicos por rol.
- Inicio de sesión con DNI de prueba y contraseña.
- **Paciente:** puede consultar disponibilidad, crear tratamientos propios, confirmar tomas y consultar su historial.
- **Cuidador:** tiene las funciones de paciente y puede registrar, consultar y confirmar tomas del paciente cuyo DNI haya vinculado a su perfil.
- **Médico:** puede usar todas las opciones anteriores, además de Dashboard y Administrar stock. En tratamientos puede indicar DNI destino, su nombre, motivo e indicaciones; puede modificar registros con un motivo obligatorio.
- Si un médico modifica un tratamiento ajeno, el paciente recibe una **notificación dentro de «Mis medicamentos»**. No se envía correo, SMS ni alerta externa.
- **Historial:** permite consultar registros por DNI en los casos permitidos y exportar CSV.
- **Roles en Perfil:** Paciente ↔ Cuidador ↔ Paciente y Cuidador. Médico puede abandonar el rol con su contraseña, pero ninguna cuenta de paciente/cuidador puede elevarse a Médico desde Perfil.
- El inventario se consulta para todos los usuarios, pero solo Médico puede agregar, editar o eliminar stock. La API también valida esos permisos.

## Datos y pruebas

El inventario, los usuarios, los tratamientos, las tomas y las notificaciones se guardan en **SQLite** del servidor; ya no exclusivamente en el navegador. Los tratamientos antiguos de localStorage no se importan automáticamente.

Las autorizaciones por DNI y la autodeclaración de Médico son **solo demostrativas**. No usar con nombres, DNI, contactos, diagnósticos ni tratamientos médicos reales. Para un sistema real serían necesarios verificación de profesionales y establecimientos, consentimiento expreso del paciente, auditoría, políticas de acceso y protección de datos.

## Ejecución local

Necesitas Python 3.9+:

```bash
python backend/server.py
```

Luego abre http://127.0.0.1:8765.

## Render (publicación)

El archivo `render.yaml` incluye la configuración necesaria. El servidor usa `PORT`, `MEDICUIDA_HOST=0.0.0.0` y `MEDICUIDA_NO_BROWSER=1`.

**Limitación del plan gratuito de Render:** SQLite usa almacenamiento efímero, por lo que usuarios, tratamientos y stock pueden desaparecer al suspenderse, reiniciarse o volver a desplegarse el servicio. Para una base de datos durable, se requiere alojamiento con almacenamiento persistente o migración a un servicio de base de datos adecuado.

Los tests automatizados están en `tests/test_seguimiento.py` y su flujo de GitHub Actions en `.github/workflows/verificar.yml`.
