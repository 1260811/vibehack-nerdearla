# 03 · Gestión de contratos

“Contrato” tiene aquí dos sentidos:

1. **Contratos técnicos:** acuerdos de formato y comportamiento entre componentes (lo que uno entrega y el otro espera). Si cambian, se rompe la integración.
2. **Contratos con terceros:** acuerdos legales y de servicio con el laboratorio y con los proveedores de infraestructura que tocan datos de salud.

## 1. Contratos técnicos

| Contrato | Productor → Consumidor | Definición | Dónde se valida |
|---|---|---|---|
| Archivo de resultado | Laboratorio → EIRA | PDF que empieza con `%PDF-`, tamaño ≤ 10 MB (`TAMANO_MAXIMO_PDF`); se guarda con nombre aleatorio y SHA-256 | `servicios.cargar_resultado` |
| Metadatos de bandeja | Laboratorio → EIRA | `.json` con el mismo nombre del PDF, ≤ 64 KB: `nombre`, `fecha_nacimiento` (AAAA-MM-DD), `folio_expediente`, `folio_laboratorio` | `servicios.importar_bandeja` |
| Ciclo de vida del documento | EIRA ↔ Médico ↔ Sistema | Solo se permiten las transiciones de `servicios.TRANSICIONES` (ver [estados](02-diagrama-de-flujo.md#estados-del-documento)) | `servicios._transicionar` |
| Aviso a la paciente | EIRA → Proveedor de correo/SMS | Plantilla fija **sin diagnóstico ni hallazgos**, con enlace único que vence en 72 h | `servicios._crear_aviso` |
| Verificación de identidad | Paciente → EIRA | Fecha de nacimiento + código de 6 dígitos (10 min); 3 errores bloquean el enlace | `servicios.validar_fecha`, `validar_codigo` |
| Bitácora | Todos → Auditoría | Solo inserción: usuario, acción, estado anterior/nuevo, detalle, fecha | `EventoBitacora.save/delete` |
| Configuración | Operación → EIRA | Variables `DJANGO_SECRET_KEY`, `EIRA_CARPETA_ENTRADA`, `EIRA_USUARIO_BANDEJA`, `EIRA_SEGUNDOS_ESPERA_BANDEJA`, `EIRA_SITIO_URL` | `eira/settings.py` |

### Cómo se gestionan

- **Fuente única:** cada contrato vive en el código que lo valida; este documento lo resume y debe actualizarse en el mismo PR que cambie el contrato.
- **Pruebas de contrato:** `resultados/tests_flujo.py` verifica cada contrato contra la aplicación real. Los `expectedFailure` documentan brechas (ver [casos de borde](../casos_borde.md)); si uno pasa inesperadamente, se revisa el contrato y se retira la marca.
- **Versionado:** un cambio incompatible (por ejemplo, un campo nuevo obligatorio en el JSON de bandeja) se acuerda con el laboratorio antes, se acepta el formato anterior durante un periodo de transición y se anuncia la fecha de corte.
- **Siguiente paso recomendado:** cuando exista una API para laboratorios, describirla en **OpenAPI** y validar el JSON de bandeja con **JSON Schema**, para que el laboratorio pueda probar sus archivos antes de enviarlos.

## 2. Contratos con terceros

| Tercero | Tipo de acuerdo | Puntos mínimos |
|---|---|---|
| Laboratorio | Convenio de servicio e intercambio de información | Formato y canal de entrega (contratos técnicos de arriba), tiempos de entrega, responsable de correcciones, confidencialidad, aviso de incidentes |
| Proveedor de correo (SES, Postmark, SendGrid) | Términos de servicio + acuerdo de tratamiento de datos | Solo recibe destino y texto sin datos clínicos; retención de registros; ubicación de los datos |
| Proveedor de SMS (Twilio, SNS) | Igual que correo | Cobertura en el país, remitente registrado, reportes de entrega para el respaldo correo → SMS → asistida |
| Nube / hosting y almacenamiento (S3, GCS, Azure) | Acuerdo de tratamiento de datos y nivel de servicio (SLA) | Cifrado en reposo y tránsito, región de alojamiento, respaldos, borrado al terminar el contrato |
| Pacientes | Aviso de privacidad y consentimiento | Finalidad, canales de contacto que autoriza, preferencia digital o asistida, derechos de acceso y corrección |

### Ciclo de gestión

1. **Alta:** antes de integrar a un tercero se revisa qué datos recibe y se firma el acuerdo.
2. **Registro:** inventario con tercero, objeto, datos que trata, vigencia, responsable interno y fecha de revisión.
3. **Seguimiento:** revisión anual o ante cualquier cambio del servicio; métricas de SLA (por ejemplo, tasa de avisos fallidos).
4. **Baja:** al terminar, se revocan credenciales y se pide constancia de borrado de datos.

> El marco legal aplicable (por ejemplo, protección de datos personales sensibles y normas del expediente clínico del país donde se implemente) debe validarse con el área jurídica; este documento no sustituye esa revisión.
