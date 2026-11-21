# 00 · Requisitos y alcance

> **Resumen:** Qué necesita la clínica en la V1, qué queda para después, qué estamos suponiendo y qué falta preguntar.

## Contexto

| Aspecto | Valor |
|---|---|
| Volumen | ~60 pacientes nuevos o atendidos por mes |
| Usuarios internos | Pocos (administración, fisioterapeutas, asistente) |
| Acceso | Por Internet, desde distintas ubicaciones |
| Infraestructura | Sin servidores físicos locales |
| Presupuesto | Lo más bajo posible |
| Crecimiento | Funcional, sin reestructuración completa |
| Región candidata | `northamerica-south1` (Querétaro, México) |

## Requisitos confirmados (V1)

1. Registrar pacientes y contactos de emergencia.
2. Mantener la historia clínica (heredofamiliares, personales patológicos y no patológicos, medicamentos).
3. Valoración clínica inicial (motivo de consulta, diagnósticos y tratamientos anteriores).
4. Registrar múltiples padecimientos por paciente.
5. Seguimiento mediante sesiones clínicas.
6. Asociar intervenciones realizadas a cada padecimiento atendido en una sesión.
7. Sugerir intervenciones según padecimientos, zonas corporales y etiquetas.
8. Almacenar fotografías, radiografías y otros archivos de imagenología.
9. Consultar la evolución histórica del paciente.

## Funcionalidades futuras (fuera de V1)

- Agenda y citas.
- Portal para pacientes.
- Facturación.

## Suposiciones (validar con la clínica)

| # | Suposición | Impacto si es falsa |
|---|---|---|
| S1 | Un paciente tiene una sola historia clínica | Cambia la cardinalidad paciente–historia |
| S2 | Las sesiones las registra un fisioterapeuta identificado | Se requiere relación sesión–usuario |
| S3 | No hay varias sucursales | Habría que agregar entidad sede |
| S4 | Los archivos no superan decenas de MB | Afecta límites de carga y costos |

## Preguntas abiertas

- ¿Quién puede ver la historia clínica completa? ¿El asistente también?
- ¿Se requiere firma o cierre de sesión clínica para impedir ediciones posteriores?
- ¿Cuánto tiempo deben conservarse los expedientes y archivos tras la última atención?
- ¿Hay que imprimir o exportar el expediente?
- ¿Las circunferencias corporales tienen un catálogo fijo de zonas?

> Agregar aquí cada pregunta nueva y registrar la respuesta con fecha y quién la dio.
