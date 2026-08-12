# Sistema de Seguimiento de Auditoría Educativa

Primera base funcional para registrar expedientes, hallazgos, recomendaciones, respuestas institucionales, evidencias y revisiones de Auditoría Interna.

## Funciones incluidas

- Usuarios con roles y alcance por institución.
- Separación segura de la configuración de desarrollo y producción.
- Expedientes, hallazgos y recomendaciones con responsables y fechas límite.
- Respuesta estructurada por recomendación.
- Carga privada de evidencias con validación de tipo, tamaño y firma del archivo.
- Versionado de respuestas y revisión por Auditoría.
- Bitácora de envíos, revisiones y descargas.
- Panel administrativo y panel web para instituciones.

## Inicio local en Windows

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe manage.py migrate
.\.venv\Scripts\python.exe manage.py seed_demo
.\.venv\Scripts\python.exe manage.py runserver
```

La primera ejecución de `seed_demo` genera credenciales temporales y las muestra una sola vez en la consola. Las ejecuciones posteriores actualizan los datos de ejemplo, pero conservan esas contraseñas. Para regenerarlas deliberadamente, use `python manage.py seed_demo --reset-passwords`. Solo debe utilizarse en desarrollo local.

## Verificaciones

```powershell
.\.venv\Scripts\python.exe manage.py check
.\.venv\Scripts\python.exe manage.py test
```

## Producción

La aplicación de producción usa `config.settings.production`, PostgreSQL y variables de entorno. Consulte [.env.example](.env.example) como inventario de configuración. El almacenamiento de evidencias debe ubicarse fuera del directorio público y conectarse con el antivirus institucional antes de habilitar descargas.

Nunca use el servidor de desarrollo ni la clave incluida en `config/settings/development.py` en un servidor institucional.
