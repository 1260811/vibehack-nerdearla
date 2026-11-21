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
│   ├── 01-decision-tecnologica.md    ← FASE 1: comparativa y costos (plantilla)
│   ├── 02-arquitectura.md            ← arquitectura candidata y recorrido de una solicitud
│   ├── 03-modelo-de-dominio.md       ← FASE 2: módulos, entidades, cardinalidades
│   ├── 04-seguridad-y-auditoria.md   ← roles, permisos, bitácora, marco legal
│   ├── 05-convenciones-bd.md         ← reglas de nombrado y diseño en PostgreSQL
│   ├── 06-archivos-e-imagenologia.md ← Cloud Storage y URLs firmadas
│   ├── 07-buenas-practicas.md        ← lineamientos generales del proyecto
│   └── adr/
│       ├── README.md
│       └── 0000-plantilla.md
├── db/
│   └── migration/
│       └── README.md                 ← orden planeado de migraciones Flyway (sin SQL aún)
└── backend/
    └── README.md                     ← estructura propuesta del backend FastAPI
```

## Fases

| Fase | Entregable | Documento | Estado |
|---|---|---|---|
| 1. Decisión tecnológica | Comparativa, costos, arquitectura, riesgos | `01`, `02` | Por hacer |
| 2. Diseño del modelo | Modelo conceptual, ER, diccionario, reglas | `03`, `04`, `05`, `06` | Por hacer |
| 3. Implementación | Migraciones Flyway, datos iniciales, conexión FastAPI | `db/`, `backend/` | Bloqueada por Fase 2 |
| 4. Validación | Pruebas de integridad, históricos, respaldo | — | Fuera de esta estructura |

## Principios del proyecto

- Clínica pequeña: ~60 pacientes/mes, pocos usuarios internos.
- Lo más **simple, económico y seguro** posible; sin microservicios, Kubernetes, Redis ni colas sin justificación concreta.
- Los registros clínicos son **históricos**: nunca se pierden al desactivar catálogos.
- La información clínica es sensible: la seguridad se aplica en el backend y la base de datos, no ocultando botones.
- Sin datos personales reales en ningún entorno que no sea producción.
