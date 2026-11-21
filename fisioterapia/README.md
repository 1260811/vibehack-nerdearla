# Sistema clínico de fisioterapia — Estructura del proyecto (V1)

Esta carpeta contiene el **esqueleto de documentación y organización** para diseñar la primera versión de un sistema de gestión clínica y seguimiento de tratamientos fisioterapéuticos en Google Cloud.

No contiene código ejecutable, scripts SQL ni pruebas: solo la estructura, las buenas prácticas y el esquema general para trabajar por fases.

## Cómo usar esta estructura

1. Trabajar **una fase a la vez**, en el orden indicado abajo.
2. Cada documento separa explícitamente:
   - **Confirmado**: requisito dado por la clínica.
   - **Recomendado**: decisión técnica propuesta (requiere aprobación).
   - **Suposición**: algo que asumimos y hay que validar.
   - **Futuro**: fuera de la V1.
3. Cada decisión importante se registra como ADR en [`docs/adr/`](docs/adr/).
4. No se genera SQL hasta cerrar la Fase 1 y aprobar el modelo de la Fase 2.

## Árbol

```
fisioterapia/
├── README.md                         ← este archivo
├── docs/
│   ├── 00-requisitos.md              ← alcance, suposiciones, preguntas abiertas
│   ├── 01-funciones-esperadas.md     ← qué debe hacer el sistema, por módulo y rol
│   ├── 02-decision-tecnologica.md    ← FASE 1: comparativa y costos (plantilla)
│   ├── 03-arquitectura.md            ← arquitectura candidata y recorrido de una solicitud
│   ├── 04-modelo-de-dominio.md       ← FASE 2: módulos, entidades, cardinalidades
│   ├── 05-seguridad-y-auditoria.md   ← roles, permisos, bitácora, marco legal
│   ├── 06-convenciones-bd.md         ← reglas de nombrado y diseño en PostgreSQL
│   ├── 07-archivos-e-imagenologia.md ← Cloud Storage y URLs firmadas
│   ├── 08-buenas-practicas.md        ← lineamientos generales del proyecto
│   └── adr/
│       ├── README.md
│       └── 0000-plantilla.md
├── db/
│   └── migration/
│       └── README.md                 ← orden planeado de migraciones Flyway (sin SQL aún)
└── backend/
    └── README.md                     ← estructura propuesta del backend FastAPI
```

## Resumen por sección

| Documento | En una línea |
|---|---|
| [`00`](docs/00-requisitos.md) Requisitos y alcance | Qué necesita la clínica en la V1, qué queda para después, qué estamos suponiendo y qué falta preguntar. |
| [`01`](docs/01-funciones-esperadas.md) Funciones esperadas | Lista de lo que el sistema debe permitir en la V1, agrupada por módulo, con quién lo hace y su prioridad. |
| [`02`](docs/02-decision-tecnologica.md) FASE 1 — Decisión tecnológica (plantilla) | Compara Firestore, Cloud SQL y PostgreSQL autoadministrado por criterios técnicos y costo en tres escenarios, y termina en una recomendación justificada. |
| [`03`](docs/03-arquitectura.md) Arquitectura candidata | Web + FastAPI + PostgreSQL + Cloud Storage privado: pocas piezas, pago por uso y seguridad en el backend. Incluye el recorrido de una solicitud. |
| [`04`](docs/04-modelo-de-dominio.md) FASE 2 — Modelo de dominio (esquema general) | Entidades por módulo y sus relaciones. Regla central: paciente → sesiones → padecimientos atendidos → intervenciones realizadas, separando lo recomendado de lo ejecutado. |
| [`05`](docs/05-seguridad-y-auditoria.md) Seguridad, auditoría y conservación | Quién puede hacer qué, cómo se registra cada acceso y cambio, cómo no perder registros clínicos y qué debe validar un especialista legal. |
| [`06`](docs/06-convenciones-bd.md) Convenciones de base de datos (PostgreSQL) | Reglas de nombrado, columnas comunes y cuándo usar catálogo, ENUM o CHECK, para que el esquema sea consistente. |
| [`07`](docs/07-archivos-e-imagenologia.md) Archivos e imagenología | Los archivos viven en un bucket privado; la base guarda solo la referencia y el backend entrega URLs firmadas temporales a usuarios autorizados. |
| [`08`](docs/08-buenas-practicas.md) Buenas prácticas del proyecto | Lineamientos de proceso, diseño, seguridad, repositorio y operación que aplican en todas las fases. |

## Fases

| Fase | Entregable | Documento | Estado |
|---|---|---|---|
| 1. Decisión tecnológica | Comparativa, costos, arquitectura, riesgos | `02`, `03` | Por hacer |
| 2. Diseño del modelo | Modelo conceptual, ER, diccionario, reglas | `01`, `04`–`07` | Por hacer |
| 3. Implementación | Migraciones Flyway, datos iniciales, conexión FastAPI | `db/`, `backend/` | Bloqueada por Fase 2 |
| 4. Validación | Pruebas de integridad, históricos, respaldo | — | Fuera de esta estructura |

## Principios del proyecto

- Clínica pequeña: ~60 pacientes/mes, pocos usuarios internos.
- Lo más **simple, económico y seguro** posible; sin microservicios, Kubernetes, Redis ni colas sin justificación concreta.
- Los registros clínicos son **históricos**: nunca se pierden al desactivar catálogos.
- La información clínica es sensible: la seguridad se aplica en el backend y la base de datos, no ocultando botones.
- Sin datos personales reales en ningún entorno que no sea producción.
