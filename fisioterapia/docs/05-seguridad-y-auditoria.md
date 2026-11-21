# 05 · Seguridad, auditoría y conservación

> **Resumen:** Quién puede hacer qué, cómo se registra cada acceso y cambio, cómo no perder registros clínicos y qué debe validar un especialista legal.

## Principios

- La autorización se valida **en el backend en cada solicitud**; ocultar botones en el frontend no es seguridad.
- Contraseñas con hash seguro y lento (Argon2id o bcrypt), nunca en texto plano ni con hash reversible.
- Mínimo privilegio: cada rol ve y hace solo lo necesario.
- Toda lectura de expediente y toda modificación clínica queda en bitácora.
- Sin usuarios administrativos con contraseñas predeterminadas en migraciones o datos iniciales.

## Matriz de permisos (borrador a validar)

| Operación | Administrador | Fisioterapeuta | Asistente |
|---|---|---|---|
| Gestionar usuarios y roles | Sí | No | No |
| Registrar / editar datos de identificación | Sí | Sí | Sí |
| Ver historia clínica completa | ¿? | Sí | ¿? |
| Registrar valoraciones y sesiones | No | Sí | No |
| Subir archivos clínicos | ¿? | Sí | ¿? |
| Ver archivos clínicos | ¿? | Sí | ¿? |
| Administrar catálogos | Sí | Sí | No |
| Consultar bitácora | Sí | No | No |

`¿?` = pendiente de decidir con la clínica.

## Bitácora

Registrar como mínimo: quién, cuándo, qué acción, sobre qué registro, desde dónde (IP/agente) y resultado.

- La bitácora es de **solo inserción**: sin `UPDATE`, sin `DELETE`, sin columna `activo`.
- Las modificaciones clínicas guardan valor anterior y nuevo, o se versionan.

## Conservación de registros clínicos

- Catálogos: borrado lógico (`activo = false`); un catálogo inactivo no aparece para nuevos registros pero sigue visible en los históricos.
- Llaves foráneas desde registros clínicos hacia catálogos con `ON DELETE RESTRICT`.
- Registros clínicos: no se eliminan físicamente; las correcciones se hacen con trazabilidad.
- Respaldos automáticos con retención definida y **prueba periódica de restauración**.
- Documentar RPO (cuánta información se puede perder) y RTO (cuánto tiempo puede estar caído).

## Marco legal (requiere validación jurídica)

Incluir columnas o funciones no equivale a cumplir la ley. Validar con un especialista:

| Tema | Referencia | Pregunta a validar |
|---|---|---|
| Datos personales sensibles | Ley Federal de Protección de Datos Personales en Posesión de los Particulares (verificar versión vigente) | Aviso de privacidad, consentimiento expreso, derechos ARCO, transferencias a la nube |
| Expediente clínico | NOM-004-SSA3-2012 | Contenido mínimo, plazo de conservación, responsables, confidencialidad |
| Sistemas de información en salud | NOM-024-SSA3-2012 | Si aplica al sistema y qué exige |
| Proveedor de nube | Contrato / términos de Google Cloud | Ubicación de datos, encargado del tratamiento |

Registrar quién validó cada punto y cuándo.
