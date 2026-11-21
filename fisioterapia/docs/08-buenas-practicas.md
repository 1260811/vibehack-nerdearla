# 08 · Buenas prácticas del proyecto

> **Resumen:** Lineamientos de proceso, diseño, seguridad, repositorio y operación que aplican en todas las fases.

## Proceso

- Trabajar por fases; no adelantar código ni SQL antes de aprobar el diseño.
- Cada decisión relevante se documenta como ADR (contexto, opciones, decisión, consecuencias).
- Separar siempre: confirmado · recomendado · suposición · futuro.
- Preguntas abiertas en `00-requisitos.md`, con respuesta, fecha y responsable.

## Diseño

- Simple antes que genérico: diseñar para una clínica pequeña que puede crecer.
- Normalizar; desnormalizar solo con una consulta concreta que lo justifique.
- Distinguir catálogo (configuración) de registro clínico (hecho histórico).
- No inventar campos clínicos no definidos; dejar como texto lo que aún no está estructurado.

## Seguridad y datos

- Nada de secretos en el repositorio; usar Secret Manager o variables de entorno no versionadas.
- Solo datos sintéticos fuera de producción.
- Mínimo privilegio en cuentas de servicio de Google Cloud.
- Bitácora de accesos a expedientes desde el primer día.

## Código y repositorio

- Ramas cortas y PRs pequeños con descripción clara.
- Migraciones Flyway inmutables: una vez aplicadas, no se editan; se crea una nueva versión.
- Mismo esquema en todos los entornos, aplicado solo por migraciones.
- Configuración por entorno (local, desarrollo, producción) sin cambios de código.

## Operación

- Respaldos automáticos y prueba de restauración documentada.
- Alertas básicas de errores y costos (presupuesto en Google Cloud).
- Revisar costos reales mensualmente contra la estimación de la Fase 1.
