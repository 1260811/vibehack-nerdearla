# Migraciones Flyway (planeadas)

> Sin SQL todavía: se escribe en la Fase 3, después de aprobar el modelo.

## Orden propuesto (por dependencias)

| Versión | Archivo | Contenido |
|---|---|---|
| V1 | `V1__catalogos.sql` | Zonas corporales, tipos de etiqueta, etiquetas, tipos de intervención, tipos de archivo, catálogos de valores |
| V2 | `V2__seguridad.sql` | Roles, usuarios, bitácora |
| V3 | `V3__pacientes_historia_clinica.sql` | Paciente, contactos de emergencia, historia clínica y antecedentes |
| V4 | `V4__padecimientos.sql` | Padecimientos y sus puentes con zonas y etiquetas |
| V5 | `V5__intervenciones.sql` | Intervenciones, puentes y `padecimiento_intervencion` |
| V6 | `V6__sesiones.sql` | Sesiones, valoraciones, `sesion_padecimiento`, `sesion_intervencion` |
| V7 | `V7__archivos.sql` | Metadatos de archivos |
| V8 | `V8__indices_y_restricciones.sql` | Índices por patrones de consulta y restricciones adicionales |
| V9 | `V9__datos_iniciales.sql` | Solo catálogos y roles; **sin usuarios ni contraseñas** |

Se puede reordenar si el modelo final cambia las dependencias.

## Reglas

- Nombre: `V<numero>__<descripcion>.sql` (dos guiones bajos).
- Una migración aplicada **nunca** se modifica; los cambios van en una versión nueva.
- Cada archivo inicia con un comentario: propósito, tablas afectadas y dependencias.
- Scripts ejecutables en una base vacía y en orden.
- Sin datos personales reales.
