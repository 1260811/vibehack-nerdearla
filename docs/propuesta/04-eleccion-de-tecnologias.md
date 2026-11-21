# 04 · Elección de tecnologías

Criterios: construir rápido en un hackathon, mantener los datos de salud bajo control (sin servicios externos en la demo) y dejar un camino claro a producción sin reescribir.

## Resumen

| Capa | Elegida | Alternativa |
|---|---|---|
| Lenguaje y framework | Python + Django 5.2 | Node.js + NestJS |
| Interfaz | Plantillas de Django (HTML + CSS, sin JavaScript de framework) | SPA con React o Vue |
| Base de datos | SQLite (demo) → PostgreSQL (producción) | MySQL / MariaDB |
| Almacenamiento de PDFs | Carpeta privada `almacen_privado/` (→ django-storages) | Amazon S3 / GCS / Azure Blob desde el inicio |
| Ingesta del laboratorio | Bandeja de carpeta compartida (PDF + JSON) | API REST para laboratorios |
| Autenticación del personal | Sesiones de Django (usuario y contraseña) | SSO con OpenID Connect (Keycloak, Entra ID) |
| Acceso de la paciente | Enlace único + fecha de nacimiento + código | Portal con cuenta de paciente |
| Avisos | Simulados (→ correo SMTP y SMS por API) | WhatsApp Business API |
| Integridad y auditoría | SHA-256 + bitácora de solo inserción | Registro inmutable externo (WORM / ledger) |
| Diagramas | Mermaid + Graphviz | PlantUML / draw.io |

## Detalle por tecnología

### Python + Django 5.2
- **Ventajas:** incluye ORM, migraciones, autenticación, sesiones, protección CSRF y administración; un solo proceso, poco código; muy usado en salud y gobierno; versión 5.2 con soporte extendido (LTS).
- **Desventajas:** monolito síncrono; escalar avisos masivos requiere cola de tareas aparte; menos atractivo si el equipo es solo JavaScript.
- **Alternativa: Node.js + NestJS.** Mismo lenguaje en frontend y backend y buen manejo de E/S concurrente, pero exige elegir y armar ORM (Prisma/TypeORM), autenticación y administración por separado.

### Plantillas de Django (renderizado en servidor)
- **Ventajas:** sin compilación ni Node; páginas ligeras que funcionan en teléfonos básicos y conexiones lentas (importante para la paciente); menos superficie de ataque.
- **Desventajas:** interacción limitada (recargas de página); difícil reutilizar en una app móvil.
- **Alternativa: React o Vue (SPA) + API.** Mejor experiencia interactiva y base para app móvil, a costa de una API, autenticación por tokens y doble mantenimiento.

### SQLite → PostgreSQL
- **Ventajas SQLite:** cero configuración, un archivo, ideal para demo y pruebas.
- **Desventajas SQLite:** una sola escritura a la vez; sin usuarios ni permisos de base de datos; no apto para varios servidores.
- **Recomendado en producción: PostgreSQL.** Concurrencia real, roles y permisos, y permite proteger la bitácora en la propia base (por ejemplo, revocar `UPDATE/DELETE` o un trigger), cerrando la brecha del ORM masivo. Django cambia de motor solo con `DATABASES`.
- **Alternativa: MySQL/MariaDB.** Igual de soportada por Django y común en hosting compartido; menos funciones avanzadas (tipos, restricciones) que PostgreSQL.

### Almacenamiento privado de PDFs
- **Ventajas:** los archivos nunca se sirven como estáticos; solo salen por vistas que verifican permiso e integridad SHA-256; nombre aleatorio sin datos de la paciente.
- **Desventajas:** disco local sin respaldo ni cifrado propio; no escala a varios servidores.
- **Alternativa: almacenamiento de objetos (S3, GCS, Azure Blob)** con `django-storages`: cifrado en reposo, versionado y respaldos gestionados; añade costo, dependencia del proveedor y acuerdo de tratamiento de datos.

### Bandeja de carpeta compartida
- **Ventajas:** el laboratorio no cambia su forma de trabajo ni necesita programar; funciona con carpeta de red, Drive/OneDrive o bucket; rechazos visibles con motivo.
- **Desventajas:** sin respuesta inmediata al laboratorio; depende de la seguridad de la carpeta; sondeo periódico.
- **Alternativa: API REST para laboratorios** (Django REST Framework + OpenAPI): validación y respuesta en el momento, autenticación por cliente; requiere que el laboratorio la integre. A futuro, **HL7 FHIR** (`DiagnosticReport`) para interoperar con sistemas clínicos.

### Sesiones de Django para el personal
- **Ventajas:** integradas, cookie `HttpOnly`, expiración a los 30 min y al cerrar el navegador.
- **Desventajas:** sin segundo factor; contraseñas por sistema.
- **Alternativa: SSO con OpenID Connect** (Keycloak, Microsoft Entra ID) con MFA y altas/bajas centralizadas; requiere un proveedor de identidad.

### Acceso de la paciente sin cuenta
- **Ventajas:** nada que recordar ni instalar; dos factores (algo que sabe: fecha; algo que tiene: el otro canal); se guarda solo la huella SHA-256 del token y del código; enlace con vencimiento y bloqueo por intentos.
- **Desventajas:** la fecha de nacimiento es un dato conocido por terceros; si la paciente tiene un solo canal, el código llega por el mismo; el PDF puede volver a descargarse durante la sesión.
- **Alternativa: portal con cuenta de paciente** (o identidad digital nacional): historial de resultados y mayor garantía de identidad, pero más fricción y barrera para pacientes con baja alfabetización digital.

### Avisos por correo y SMS
- **Ventajas:** el mensaje no lleva información clínica; dos canales permiten respaldo; proveedores estándar (Amazon SES, Postmark, SendGrid por SMTP de Django; Twilio o Amazon SNS para SMS).
- **Desventajas:** costo por SMS; correos que caen en spam; en la demo todo es simulado y no hay reportes reales de entrega.
- **Alternativa: WhatsApp Business API.** Es el canal que la paciente ya usa y tiene confirmación de lectura, pero requiere plantillas aprobadas por Meta, costo por conversación y un tercero más que trata datos; nunca debe llevar el PDF, solo el enlace.

### SHA-256 + bitácora de solo inserción
- **Ventajas:** detecta si el PDF cambió desde que se cargó; trazabilidad de cada acción y acceso.
- **Desventajas:** la bitácora vive en la misma base y un administrador con acceso directo podría alterarla.
- **Alternativa: registro inmutable externo** (almacenamiento WORM como S3 Object Lock, o un servicio de logs centralizado) para auditoría a prueba de manipulación.

### Mermaid + Graphviz para diagramas
- **Ventajas:** diagramas como texto, versionados con el código; GitHub muestra Mermaid sin herramientas extra; Graphviz genera PNG sin Node.
- **Desventajas:** control limitado del diseño visual.
- **Alternativa: PlantUML o draw.io** para diagramas UML más completos o edición visual.
