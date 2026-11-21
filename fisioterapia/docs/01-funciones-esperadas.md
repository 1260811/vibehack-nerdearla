# 01 · Funciones esperadas

> **Resumen:** Lista de lo que el sistema debe permitir en la V1, agrupada por módulo, con quién lo hace y su prioridad. Es la base para validar el modelo de datos y la arquitectura: si una función no cabe en el modelo, el modelo está incompleto.

Roles (borrador, ver `05-seguridad-y-auditoria.md`): **ADM** administrador · **FT** fisioterapeuta · **AS** asistente.

Prioridad: **Esencial** (sin esto no hay V1) · **Deseable** (V1 si alcanza) · **Futuro**.

## Pacientes

| Id | Función | Rol | Prioridad |
|---|---|---|---|
| F-PAC-01 | Registrar paciente con datos de identificación | FT, AS | Esencial |
| F-PAC-02 | Editar datos de identificación (con bitácora) | FT, AS | Esencial |
| F-PAC-03 | Registrar uno o varios contactos de emergencia | FT, AS | Esencial |
| F-PAC-04 | Buscar paciente por nombre, apellidos o fecha de nacimiento | FT, AS | Esencial |
| F-PAC-05 | Desactivar paciente sin borrar su historial | ADM | Deseable |

## Historia clínica

| Id | Función | Rol | Prioridad |
|---|---|---|---|
| F-HC-01 | Registrar antecedentes heredofamiliares (enfermedad, parentesco, observaciones) | FT | Esencial |
| F-HC-02 | Registrar antecedentes personales patológicos (enfermedades, traumatismos, cirugías, transfusiones, alergias, aditamentos) | FT | Esencial |
| F-HC-03 | Registrar antecedentes no patológicos (factores Bueno/Regular/Malo y hábitos) | FT | Esencial |
| F-HC-04 | Registrar medicamentos actuales | FT | Esencial |
| F-HC-05 | Consultar la historia clínica completa | FT | Esencial |

## Valoración y seguimiento

| Id | Función | Rol | Prioridad |
|---|---|---|---|
| F-VAL-01 | Registrar valoración inicial (motivo de consulta, diagnósticos y tratamientos anteriores) | FT | Esencial |
| F-VAL-02 | Registrar signos vitales (FC, FR, TA sistólica/diastólica, temperatura, oximetría) | FT | Esencial |
| F-VAL-03 | Registrar medidas antropométricas (peso, talla, circunferencias por zona) | FT | Esencial |
| F-VAL-04 | Registrar exploración física | FT | Esencial |
| F-VAL-05 | Repetir signos, medidas y exploración en sesiones posteriores | FT | Esencial |
| F-VAL-06 | Ver IMC calculado | FT | Deseable |

## Sesiones clínicas

| Id | Función | Rol | Prioridad |
|---|---|---|---|
| F-SES-01 | Crear sesión clínica para un paciente | FT | Esencial |
| F-SES-02 | Agregar uno o varios padecimientos atendidos en la sesión | FT | Esencial |
| F-SES-03 | Registrar las intervenciones realizadas por padecimiento (series, repeticiones, duración, intensidad, indicaciones) | FT | Esencial |
| F-SES-04 | Ver sugerencias de intervenciones según padecimiento, zona y etiquetas | FT | Esencial |
| F-SES-05 | Consultar el historial cronológico de sesiones del paciente | FT | Esencial |
| F-SES-06 | Ver la evolución de un padecimiento a lo largo de las sesiones | FT | Deseable |

## Catálogos

| Id | Función | Rol | Prioridad |
|---|---|---|---|
| F-CAT-01 | Administrar padecimientos y asociarlos a zonas y etiquetas | ADM, FT | Esencial |
| F-CAT-02 | Administrar zonas corporales | ADM | Esencial |
| F-CAT-03 | Administrar etiquetas y sus tipos | ADM, FT | Esencial |
| F-CAT-04 | Administrar intervenciones y tipos de intervención | ADM, FT | Esencial |
| F-CAT-05 | Configurar recomendaciones padecimiento–intervención (prioridad, activo) | FT | Esencial |
| F-CAT-06 | Desactivar elementos de catálogo sin afectar registros anteriores | ADM | Esencial |

## Archivos e imagenología

| Id | Función | Rol | Prioridad |
|---|---|---|---|
| F-ARC-01 | Subir archivo al expediente o a una sesión | FT | Esencial |
| F-ARC-02 | Clasificar archivo por tipo (fotografía, radiografía, resonancia, ultrasonido, PDF, otro) | FT | Esencial |
| F-ARC-03 | Ver o descargar archivo mediante URL temporal | FT | Esencial |
| F-ARC-04 | Listar archivos del paciente por fecha y tipo | FT | Esencial |

## Seguridad y administración

| Id | Función | Rol | Prioridad |
|---|---|---|---|
| F-SEG-01 | Iniciar y cerrar sesión | Todos | Esencial |
| F-SEG-02 | Crear, desactivar usuarios y asignar rol | ADM | Esencial |
| F-SEG-03 | Cambiar la propia contraseña | Todos | Esencial |
| F-SEG-04 | Registrar en bitácora accesos a expedientes y cambios clínicos | Sistema | Esencial |
| F-SEG-05 | Consultar bitácora | ADM | Deseable |

## Futuro (fuera de V1)

- Agenda y citas.
- Portal o acceso para pacientes.
- Reportes estadísticos de la clínica.
- Exportar o imprimir expediente completo (confirmar si se necesita en V1).

## Cómo usar esta lista

- Cada función debe poder trazarse a entidades del modelo (`04`) y a endpoints del backend.
- Si la clínica agrega o quita funciones, se actualiza aquí primero.
