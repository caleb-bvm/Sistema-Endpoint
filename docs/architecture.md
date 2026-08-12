# Arquitectura inicial

## Objetivo

Mantener en un único expediente verificable el informe, los hallazgos, las recomendaciones, las respuestas institucionales, las evidencias y las decisiones de Auditoría Interna.

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

## Decisiones pendientes de infraestructura

- Integración con antivirus o sistema de análisis utilizado por el Ministerio.
- Directorio institucional, LDAP o Active Directory.
- Almacenamiento NAS o compatible con S3.
- Servidor SMTP institucional.
- Política definitiva de respaldo y retención.
- Dominio, certificado y segmentación de red.
