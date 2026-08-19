# Plan de catálogo institucional y cuentas de acceso

## Decisión recomendada

El sistema debe **precargar el catálogo completo de centros educativos y dependencias**, pero **activar las cuentas institucionales solamente cuando sean necesarias**.

Las instituciones, las cuentas y las personas que integran el CDE representan objetos distintos:

- La institución debe existir desde el inicio para poder asignarle expedientes y recomendaciones, aunque todavía no tenga usuarios.
- Cada centro habilitado utiliza una cuenta institucional única que representa al centro, no a una persona particular.
- Las personas que ejercieron la administración y representación legal se registran en el historial del CDE, con su período, cargo y documento de respaldo.

Esta estrategia evita más de mil credenciales inactivas y contraseñas distribuidas anticipadamente. También evita que cada auditor tenga que volver a capturar los datos del centro y mantiene separada la actividad de la cuenta institucional del historial legal de sus administradores.

## Estado temporal del piloto

La interfaz de Dirección permite buscar centros y activar su acceso con el usuario `centro.<código>`. Durante la validación local, la cuenta activada reutiliza la credencial común de demostración y no exige un cambio inmediato. Antes de publicar el sistema, esa credencial común debe sustituirse por una credencial institucional propia para cada centro y entregarse mediante un canal seguro.

## Distribución de responsabilidades

| Actividad | Responsable propuesto |
| --- | --- |
| Entregar y depurar el catálogo oficial | Unidad dueña del directorio de centros |
| Importar o actualizar el catálogo | Administración técnica |
| Solicitar la activación del centro | Auditor asignado o jefatura responsable |
| Crear o suspender la cuenta institucional | Administración de Auditoría |
| Registrar y mantener el CDE | Centro educativo mediante su cuenta institucional |
| Atender problemas técnicos | Administración técnica |

El auditor puede iniciar la solicitud de activación, pero no debería definir contraseñas ni crear usuarios directamente. La conformación del CDE no requiere aprobación ni mantenimiento por parte del auditor o de la Dirección de Auditoría.

## Flujo de activación bajo demanda

1. El catálogo institucional se carga desde la fuente oficial utilizando el código único del centro.
2. Al asignar la primera recomendación a un centro sin usuarios activos, el sistema debe advertirlo a Auditoría.
3. El auditor solicita la activación del centro.
4. Se crea o reactiva la cuenta institucional vinculada al código oficial del centro.
5. El centro utiliza esa cuenta para atender sus expedientes y mantener el historial de su CDE.
6. La cuenta se suspende cuando el centro deja de estar activo o pierde autorización de acceso al sistema.

Cada centro mantiene una sola cuenta institucional activa. Sus actuaciones quedan atribuidas al centro en la bitácora; cuando una actuación requiera identificar a una persona, se conserva el nombre y cargo declarado dentro de la propia actuación.

## Carga inicial

Para el piloto se recomienda:

- Importar todo el catálogo oficial disponible.
- Activar solamente entre 5 y 20 centros participantes.
- Confirmar códigos duplicados, centros cerrados y cambios de nombre antes de ampliar el uso.
- Conservar el código institucional como identificador estable; el nombre puede actualizarse.

El comando `python manage.py import_organizations archivo.csv --dry-run` valida el archivo sin modificar datos. Una vez revisado, se ejecuta sin `--dry-run` para crear o actualizar el catálogo.

Columnas admitidas:

| Columna | Obligatoria | Ejemplo |
| --- | --- | --- |
| `code` | Sí | `10754` |
| `name` | Sí | `Instituto Nacional de Nahuizalco` |
| `kind` | No | `educational_center` |
| `department` | No | `Sonsonate` |
| `municipality` | No | `Nahuizalco` |
| `address` | No | `Dirección institucional` |
| `is_active` | No | `true` |

## Controles necesarios antes del despliegue general

- Entregar la credencial únicamente mediante el canal oficial definido para el centro.
- Registrar creación, activación y suspensión de la cuenta institucional en la bitácora.
- Definir un tiempo máximo para atender solicitudes de acceso.
- Integrar el directorio institucional, LDAP o Active Directory cuando la infraestructura esté disponible.

## Fases propuestas

1. **Piloto:** catálogo completo y activación manual controlada de 5 a 20 centros.
2. **Expansión:** formulario interno de solicitud y activación, historial del CDE y reportes de cuentas pendientes.
3. **Operación institucional:** integración con directorio institucional y recuperación automatizada de la cuenta del centro.
