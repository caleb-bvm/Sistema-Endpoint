# Arquitectura inicial

## Objetivo

Mantener en un único expediente verificable el informe, los hallazgos, las recomendaciones, las respuestas institucionales, las evidencias y las decisiones de Auditoría Interna.

El expediente funciona además como historial permanente del centro. Los informes anteriores
se registran como documentos anteriores y sus recomendaciones no cumplidas o parcialmente
cumplidas pueden incorporarse, conservando su procedencia, a un seguimiento posterior.

## Componentes

- **Django:** autenticación, reglas de acceso, flujo de expedientes, formularios y generación de constancias.
- **PostgreSQL:** datos estructurados, relaciones, estados y bitácora.
- **Almacenamiento privado:** informes y evidencias con nombres internos aleatorios.
- **Nginx:** terminación HTTPS, límites de solicitudes y entrega de contenido estático.
- **Antivirus institucional:** aprobación de archivos antes de permitir su descarga en producción.

El entorno local utiliza SQLite para simplificar el desarrollo. La configuración de producción exige PostgreSQL y no admite valores predeterminados para secretos o dominios.

## Límites de acceso

- Un responsable institucional ve los expedientes de su institución o aquellos que contengan recomendaciones asignadas a ella.
- Un auditor ve solamente los expedientes que tiene asignados.
- Un administrador de Auditoría puede consultar todos los expedientes.
- El administrador técnico mantiene la plataforma, pero sus actuaciones también quedan sujetas a bitácora.
- Cada descarga pasa por una comprobación de autorización; los archivos no tienen una dirección pública directa.

## Estados principales

### Expediente

1. Borrador.
2. Pendiente de aprobación directiva.
3. Enviado.
4. En respuesta.
5. En revisión.
6. Requiere corrección.
7. Cierre solicitado.
8. Cerrado.

La publicación y el cierre requieren una decisión de la Dirección de Auditoría. El auditor asignado prepara y solicita; la directora aprueba o devuelve con una justificación inalterable. La reasignación de auditor también exige un fundamento y se registra en la bitácora.

### Recomendación

1. Pendiente.
2. Respuesta enviada.
3. En revisión.
4. Requiere corrección.
5. Cumplida, parcialmente cumplida o no cumplida.

## Archivos

Los formatos iniciales permitidos son PDF, JPG, PNG, DOCX y XLSX. La validación comprueba extensión, tamaño, firma básica y estructura interna de los documentos de Office. En producción, `FILE_SCAN_REQUIRED=true` mantiene los archivos sin disponibilidad hasta que el servicio antivirus los marque como aprobados.

Los nuevos informes se elaboran fuera del sistema y se cargan en Word. Cada carga crea una
versión independiente. La Dirección aprueba o devuelve el informe completo; solamente la
versión aprobada se publica para la institución. Los PDF y Word anteriores se conservan en el
repositorio de informes anteriores.

Las respuestas institucionales siempre requieren al menos un documento. La validación rechaza
el envío si no se adjunta ningún archivo. Una institución puede
consultar sus propias respuestas y evidencias, pero no los archivos privados enviados por otras
dependencias que participen en el mismo expediente.

## Plazos y conservación

- Toda prórroga conserva la fecha anterior, los días hábiles concedidos, la nueva fecha, el motivo y el usuario que la registró.
- Los fines de semana y los asuetos activos se excluyen del cálculo.
- El comando `process_overdue_recommendations` registra como no cumplidas las recomendaciones sin respuesta cuyo plazo vigente ya terminó. Solo procesa expedientes publicados y respeta la prórroga más reciente.
- Los expedientes publicados no se eliminan. Las correcciones se realizan mediante nuevas versiones y todas las actuaciones quedan en la bitácora.

## Consejo Directivo Escolar

- Cada centro educativo administra con su cuenta institucional los períodos e integrantes de su Consejo Directivo Escolar (CDE).
- Cada período conserva sus fechas, años escolares, acta de conformación e integrantes. Solamente un período puede figurar como vigente por centro.
- Registrar un nuevo CDE finaliza el estado vigente del anterior sin eliminarlo. Las salidas y sustituciones conservan a la persona dentro del período histórico.
- Auditoría y Dirección consultan esta información, pero no la aprueban ni son responsables de mantenerla.
- Las correcciones conservan en la bitácora los valores anteriores y nuevos. No existen acciones de eliminación en la interfaz ni en la administración técnica.
- Los documentos del CDE permanecen en almacenamiento privado y pasan por la misma validación de formato y autorización aplicada al resto de los documentos institucionales.
- Cada respuesta institucional conserva una referencia al CDE que estaba vigente al presentarla. Un cambio posterior de período no modifica esa referencia histórica.

## Decisiones pendientes de infraestructura

- Integración con antivirus o sistema de análisis utilizado por el Ministerio.
- Directorio institucional, LDAP o Active Directory.
- Almacenamiento NAS o compatible con S3.
- Servidor SMTP institucional.
- Política definitiva de respaldo y retención.
- Dominio, certificado y segmentación de red.
