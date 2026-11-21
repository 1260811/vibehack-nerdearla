# 05 · Convenciones de base de datos (PostgreSQL)

Aplican solo si la Fase 1 confirma PostgreSQL.

## Nombrado

| Elemento | Regla | Ejemplo |
|---|---|---|
| Tablas | `snake_case`, singular | `sesion_clinica` |
| Columnas | `snake_case` | `fecha_nacimiento` |
| Clave primaria | `id BIGSERIAL` | `id` |
| Llave foránea | `<entidad>_id` | `paciente_id` |
| Tabla puente | `<entidad_a>_<entidad_b>` | `padecimiento_zona` |
| Índice | `ix_<tabla>__<columnas>` | `ix_sesion_clinica__paciente_id_fecha` |
| Único | `uq_<tabla>__<columnas>` | `uq_zona_corporal__nombre` |
| Check | `ck_<tabla>__<regla>` | `ck_signos_vitales__oximetria_rango` |
| Llave foránea (constraint) | `fk_<tabla>__<referencia>` | `fk_sesion_clinica__paciente` |

## Columnas comunes

| Columna | Dónde | Regla |
|---|---|---|
| `created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP` | Todas | — |
| `updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP` | Tablas editables | Actualizar desde el backend o con trigger |
| `activo BOOLEAN NOT NULL DEFAULT TRUE` | Catálogos y entidades que se "desactivan" | **No** en bitácora ni en registros históricos sin justificar su significado |

Evaluar `TIMESTAMPTZ` frente a `TIMESTAMP` y documentar la decisión (zona horaria del servidor vs. de la clínica).

## Reglas de diseño

- Cada relación N:M tiene su tabla puente con `UNIQUE (a_id, b_id)`.
- Llaves foráneas siempre declaradas; `ON DELETE RESTRICT` hacia catálogos.
- `CHECK` para rangos clínicos razonables (FC, FR, TA, temperatura, oximetría, peso, talla).
- Índices solo según patrones de consulta reales (p. ej. historial por paciente y fecha).
- Unidades explícitas en el nombre o en el diccionario (`peso_kg`, `talla_cm`, `temperatura_c`).
- `NUMERIC` para medidas con decimales fijos; evitar `FLOAT` en datos clínicos.
- `JSONB` solo con justificación concreta, nunca como sustituto del modelo relacional.
- No convertir cada atributo en catálogo ni cada relación en una abstracción genérica.

## ENUM vs. catálogo vs. CHECK

| Opción | Usar cuando | Evitar cuando |
|---|---|---|
| `CHECK (col IN (...))` | Pocos valores, estables, sin atributos | Los usuarios necesitan editarlos |
| `ENUM` | Valores muy estables y conocidos | Habrá altas/bajas frecuentes (alterar ENUM es más rígido) |
| Catálogo relacional | Valores editables, con atributos o que deben desactivarse | Lista trivial e inmutable |
