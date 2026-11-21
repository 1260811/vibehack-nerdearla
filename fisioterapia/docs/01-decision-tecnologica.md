# 01 · FASE 1 — Decisión tecnológica (plantilla)

> Regla: **no generar SQL** hasta cerrar esta fase. Los costos se toman de las páginas oficiales de precios de Google Cloud, con fecha de consulta.

## Alternativas

| Id | Alternativa | Tipo |
|---|---|---|
| A | Cloud Firestore | NoSQL documental, serverless |
| B | Cloud SQL for PostgreSQL | Relacional administrada |
| C | PostgreSQL en Compute Engine | Relacional autoadministrada (solo referencia) |
| D | Otra (justificar) | — |

## Comparativa cualitativa

Calificar cada criterio (Alto / Medio / Bajo) y justificar en una línea.

| Criterio | A Firestore | B Cloud SQL | C Compute Engine |
|---|---|---|---|
| Costo mensual mínimo real | | | |
| Costos fijos vs variables | | | |
| Relaciones N:M | | | |
| Integridad referencial | | | |
| Transacciones | | | |
| Consultas históricas | | | |
| Búsquedas multicriterio | | | |
| Complejidad del backend | | | |
| Mantenimiento | | | |
| Escalabilidad | | | |
| Respaldos y recuperación | | | |
| Seguridad | | | |
| Facilidad de migración | | | |
| Dependencia del proveedor | | | |

## Escenarios económicos

Separar siempre: **base de datos · almacenamiento de imágenes · backend · otros** (red, respaldos, secretos, logs).

| Concepto | 1. Desarrollo/pruebas | 2. Producción económica | 3. Producción con mayor disponibilidad |
|---|---|---|---|
| Base de datos | | | |
| Almacenamiento de imágenes | | | |
| Backend | | | |
| Respaldos | | | |
| Red / transferencia | | | |
| Otros | | | |
| **Total USD** | | | |
| **Total MXN** (tipo de cambio: ___ , fecha: ___) | | | |

Supuestos por escenario (tamaño de BD, GB de imágenes, horas activas, número de solicitudes):

- Escenario 1: …
- Escenario 2: …
- Escenario 3: …

Cuidados al calcular:

- Una instancia de Cloud SQL de núcleo compartido sirve para desarrollo, pero **no** debe presentarse como producción con SLA.
- Verificar que todos los servicios existan y tengan precio publicado en `northamerica-south1`.
- Incluir costo de respaldos y retención, no solo la instancia.

## Recomendación

- **Opción elegida:** …
- **Justificación técnica:** …
- **Riesgos y limitaciones:** …
- **Condiciones que harían cambiar la decisión:** …

Registrar la decisión final como ADR (`adr/0001-…`).

## Fuentes consultadas

| Fuente | URL | Fecha de consulta |
|---|---|---|
| Precios Cloud SQL | https://cloud.google.com/sql/pricing | |
| Precios Firestore | https://cloud.google.com/firestore/pricing | |
| Precios Cloud Storage | https://cloud.google.com/storage/pricing | |
| Precios Cloud Run | https://cloud.google.com/run/pricing | |
| Precios Compute Engine | https://cloud.google.com/compute/all-pricing | |
| SLA Cloud SQL | https://cloud.google.com/sql/sla | |
