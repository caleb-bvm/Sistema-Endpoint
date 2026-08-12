# Plan de catálogo institucional y cuentas de acceso

## Decisión recomendada

El sistema debe **precargar el catálogo completo de centros educativos y dependencias**, pero **no crear automáticamente una cuenta por cada centro**.

Las instituciones y las cuentas representan objetos distintos:

- La institución debe existir desde el inicio para poder asignarle expedientes y recomendaciones, aunque todavía no tenga usuarios.
- Cada cuenta debe corresponder a una persona identificada, con cargo, correo verificado y responsabilidad vigente.

Esta estrategia evita más de mil credenciales inactivas, contraseñas distribuidas anticipadamente y cuentas compartidas difíciles de auditar. También evita que cada auditor tenga que volver a capturar los datos del centro.

## Distribución de responsabilidades

| Actividad | Responsable propuesto |
| --- | --- |
| Entregar y depurar el catálogo oficial | Unidad dueña del directorio de centros |
| Importar o actualizar el catálogo | Administración técnica |
| Solicitar acceso para una persona | Auditor asignado o jefatura responsable |
| Verificar identidad, cargo y correo | Administración de Auditoría |
| Crear, suspender o reasignar cuentas | Administración de Auditoría |
| Atender problemas técnicos | Administración técnica |

El auditor puede iniciar la solicitud, pero no debería definir contraseñas ni crear usuarios directamente. Esta separación reduce errores y deja una responsabilidad clara sobre la autorización de acceso.

## Flujo de activación bajo demanda

1. El catálogo institucional se carga desde la fuente oficial utilizando el código único del centro.
2. Al asignar la primera recomendación a un centro sin usuarios activos, el sistema debe advertirlo a Auditoría.
3. El auditor solicita la activación e identifica al responsable designado por el centro.
4. Administración de Auditoría verifica nombre, cargo, correo y vigencia de la designación.
5. Se crea una cuenta personal vinculada al centro. Nunca se crea una cuenta genérica compartida si es posible identificar al responsable.
6. La persona recibe un mecanismo de activación temporal y debe cambiar la contraseña en el primer ingreso.
7. La cuenta se revisa periódicamente y se suspende cuando cambia el responsable o el centro deja de estar activo.

Un centro puede tener más de una cuenta nominal si existe una necesidad aprobada. Todas quedan vinculadas a la misma institución y sus actuaciones se registran individualmente en la bitácora.

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

- Prohibir cuentas compartidas y exigir cuentas nominales.
- Verificar el correo o canal oficial antes de entregar acceso.
- Forzar cambio de contraseña en el primer ingreso; esta función ya existe en la base actual.
- Registrar creación, activación, suspensión y cambio de institución en la bitácora.
- Definir un tiempo máximo para atender solicitudes de acceso.
- Realizar una recertificación de cuentas al menos cada seis meses.
- Integrar el directorio institucional, LDAP o Active Directory cuando la infraestructura esté disponible.

## Fases propuestas

1. **Piloto:** catálogo completo y activación manual controlada de 5 a 20 centros.
2. **Expansión:** formulario interno de solicitud y activación, alertas de centros sin usuario y reportes de cuentas pendientes.
3. **Operación institucional:** integración con directorio institucional, recuperación automatizada y recertificación periódica.
