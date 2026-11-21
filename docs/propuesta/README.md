# Propuesta de solución EIRA

Documentación de la propuesta para la entrega segura de resultados de Papanicolaou. Describe lo que hace el prototipo actual y marca como **pendiente** lo que todavía no existe.

| Documento | Contenido |
|---|---|
| [01 · Casos de uso](01-casos-de-uso.md) | Actores, casos de uso con flujo principal, alternativos y estado en el prototipo |
| [02 · Diagrama de flujo](02-diagrama-de-flujo.md) | Proceso de negocio de punta a punta, secuencia del acceso de la paciente y estados del documento |
| [03 · Gestión de contratos](03-gestion-de-contratos.md) | Contratos técnicos entre componentes (formatos, estados, avisos) y acuerdos con terceros (laboratorio, proveedores, nube) |
| [04 · Elección de tecnologías](04-eleccion-de-tecnologias.md) | Cada tecnología elegida con ventajas, desventajas y una alternativa |

Documentos técnicos ya existentes: [flujo real y matriz de permisos](../diagrama_flujo.md) y [casos de borde](../casos_borde.md).

## Resumen

- **Problema:** hoy el resultado se escanea, se busca el teléfono de la paciente y se envía por WhatsApp, sin verificar identidad, sin autorización clínica registrada y sin rastro de quién lo vio.
- **Propuesta:** un recorrido controlado `Cargado → Asociado → Revisado → Autorizado → Notificado → Consultado`, con verificación de identidad al asociar, autorización médica por una persona distinta de quien revisó, aviso sin información clínica, acceso de la paciente por enlace único + fecha de nacimiento + código de un solo uso, y bitácora de solo inserción.
- **Tecnología base:** Django 5.2 (Python) con SQLite en la demo y PostgreSQL recomendado para uso real; almacenamiento privado de PDFs; avisos simulados con camino definido hacia correo (SES/Postmark/SendGrid) y SMS (Twilio/SNS).
