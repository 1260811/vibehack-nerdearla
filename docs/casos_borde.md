# Casos de borde del flujo real

Generado con `python3 manage.py probar_flujo` sobre una base aislada de pruebas.

✅ = contrato satisfecho; ❌ = brecha reproducida (fallo esperado), no una protección implementada.
Los contratos de funciones/campos ausentes comprueban ausencia, no simulan una implementación.
No se probaron proveedores reales, OCR, conectividad ni despliegue productivo.

## Reejecución contra la rama principal actualizada

Antes de cambios: suite completa 57 pruebas, 12 fallos esperados; tester 29 pruebas, 12 fallos esperados. Sin éxitos inesperados.
Respecto al primer tester: ✅ enlace con caducidad de 72 h y ✅ preferencia asistida ya resueltos en main.
✅ Nuevo control comprobado: respaldo simulado correo→SMS→asistencia. ❌ Integración de proveedor real aún ausente.
❌ Nuevas brechas: entradas de fecha malformadas sin límite/auditoría y solicitudes de código sin límite de frecuencia.
Los cambios de esta rama solo amplían pruebas y documentación: no corrigen la aplicación.

Escenarios: 43. Brechas esperadas: 14. Fallos inesperados: 0.

| Escenario | Actor | Esperado | Obtenido | Estado | Riesgo/recomendación |
|---|---|---|---|---|---|
| antes de autorizar no existe enlace emitido y un identificador de resultado no sirve como token. | Paciente | antes de autorizar no existe enlace emitido y un identificador de resultado no sirve como token. | Contrato satisfecho en la aplicación real. | ✅ | Mantener esta protección y su prueba. |
| plantilla alterada admite diagnóstico sin filtro | EIRA | Rechazar cualquier aviso con diagnóstico o hallazgos. | Brecha reproducida: plantilla alterada admite diagnóstico sin filtro. | ❌ | validar antes de guardar. |
| aviso predeterminado no revela hallazgos ni diagnóstico. | EIRA | aviso predeterminado no revela hallazgos ni diagnóstico. | Contrato satisfecho en la aplicación real. | ✅ | Mantener esta protección y su prueba. |
| el aviso contiene enlace pero no código, enviado aparte por SMS si el aviso fue por correo. | Sistema | el aviso contiene enlace pero no código, enviado aparte por SMS si el aviso fue por correo. | Contrato satisfecho en la aplicación real. | ✅ | Mantener esta protección y su prueba. |
| bandeja bloquea folio previamente cargado, a diferencia de carga manual. | Laboratorio | bandeja bloquea folio previamente cargado, a diferencia de carga manual. | Contrato satisfecho en la aplicación real. | ✅ | Mantener esta protección y su prueba. |
| PDF sin datos se rechaza, archiva y audita. | Laboratorio | PDF sin datos se rechaza, archiva y audita. | Contrato satisfecho en la aplicación real. | ✅ | Mantener esta protección y su prueba. |
| bandeja vacía no genera documentos ni rechazos. | Laboratorio | bandeja vacía no genera documentos ni rechazos. | Contrato satisfecho en la aplicación real. | ✅ | Mantener esta protección y su prueba. |
| QuerySet.update evita save y altera bitácora | Sistema | Impedir cambios de bitácora también mediante ORM masivo. | Brecha reproducida: QuerySet.update evita save y altera bitácora. | ❌ | proteger en base de datos. |
| modificar o borrar una instancia de bitácora está bloqueado. | EIRA | modificar o borrar una instancia de bitácora está bloqueado. | Contrato satisfecho en la aplicación real. | ✅ | Mantener esta protección y su prueba. |
| cargador con cambio de rol puede autorizar | Médico | Impedir que la identidad cargadora autorice clínicamente. | Brecha reproducida: cargador con cambio de rol puede autorizar. | ❌ | separar carga y autorización. |
| código caducado se rechaza aunque el enlace siga vigente. | Paciente | código caducado se rechaza aunque el enlace siga vigente. | Contrato satisfecho en la aplicación real. | ✅ | Mantener esta protección y su prueba. |
| código incorrecto no acredita identidad ni entrega documento. | Paciente | código incorrecto no acredita identidad ni entrega documento. | Contrato satisfecho en la aplicación real. | ✅ | Mantener esta protección y su prueba. |
| al solicitar otro código el anterior deja de ser válido. | Paciente | al solicitar otro código el anterior deja de ser válido. | Contrato satisfecho en la aplicación real. | ✅ | Mantener esta protección y su prueba. |
| conocer el código sin validar fecha en esa sesión no abre el documento. | Paciente | conocer el código sin validar fecha en esa sesión no abre el documento. | Contrato satisfecho en la aplicación real. | ✅ | Mantener esta protección y su prueba. |
| no existe versión/revocación ni reaviso | EIRA | Ofrecer corrección versionada, reaviso y revocación de la versión anterior. | Brecha reproducida: no existe versión/revocación ni reaviso. | ❌ | impedir acceso a versión anterior. |
| saltos de estado denegados no dejan evento | Médico | Registrar un evento incluso cuando se rechaza una transición. | Brecha reproducida: saltos de estado denegados no dejan evento. | ❌ | auditar todos los rechazos. |
| carga manual repite hash y folio | Laboratorio | Rechazar una segunda carga del mismo documento/folio. | Brecha reproducida: carga manual repite hash y folio. | ❌ | deduplicar también fuera de bandeja. |
| enlace caducado deniega también el PDF de una sesión previamente verificada. | Paciente | enlace caducado deniega también el PDF de una sesión previamente verificada. | Contrato satisfecho en la aplicación real. | ✅ | Mantener esta protección y su prueba. |
| verificar un enlace no habilita el enlace de otra paciente ni su PDF. | Paciente | verificar un enlace no habilita el enlace de otra paciente ni su PDF. | Contrato satisfecho en la aplicación real. | ✅ | Mantener esta protección y su prueba. |
| tras verificar, el PDF se puede volver a descargar mientras dure la sesión (30 min). | Paciente | Limitar la descarga a un solo uso tras verificar la identidad. | Brecha reproducida: tras verificar, el PDF se puede volver a descargar mientras dure la sesión (30 min).. | ❌ | Mantener esta protección y su prueba. |
| el respaldo correo→SMS→asistida es simulado | Sistema | Ofrecer respaldo ante falla de correo, después SMS y finalmente asistencia. | Brecha reproducida: el respaldo correo→SMS→asistida es simulado. | ❌ | falta proveedor real que reporte fallas. |
| dos fallas simuladas correo y SMS derivan a entrega asistida y revocación. | Sistema/EIRA | dos fallas simuladas correo y SMS derivan a entrega asistida y revocación. | Contrato satisfecho en la aplicación real. | ✅ | Mantener esta protección y su prueba. |
| fecha incorrecta no emite código, deniega PDF y registra un intento. | Paciente | fecha incorrecta no emite código, deniega PDF y registra un intento. | Contrato satisfecho en la aplicación real. | ✅ | Mantener esta protección y su prueba. |
| fechas vacías o malformadas no consumen intentos ni se auditan | Paciente | Contabilizar y bloquear entradas inválidas tras tres intentos, igual que fechas incorrectas. | Brecha reproducida: fechas vacías o malformadas no consumen intentos ni se auditan. | ❌ | limitar también entradas inválidas. |
| tres errores repartidos entre sesiones bloquean el enlace y requieren asistencia. | Paciente | tres errores repartidos entre sesiones bloquean el enlace y requieren asistencia. | Contrato satisfecho en la aplicación real. | ✅ | Mantener esta protección y su prueba. |
| homónimos con fecha y expediente diferentes no se confunden. | EIRA | homónimos con fecha y expediente diferentes no se confunden. | Contrato satisfecho en la aplicación real. | ✅ | Mantener esta protección y su prueba. |
| un folio discrepante bloquea y audita la asociación. | EIRA | un folio discrepante bloquea y audita la asociación. | Contrato satisfecho en la aplicación real. | ✅ | Mantener esta protección y su prueba. |
| revisión humana devuelve escaneo ilegible con motivo. | EIRA | revisión humana devuelve escaneo ilegible con motivo. | Contrato satisfecho en la aplicación real. | ✅ | Mantener esta protección y su prueba. |
| otro usuario de laboratorio no puede acceder al documento. | Laboratorio | otro usuario de laboratorio no puede acceder al documento. | Contrato satisfecho en la aplicación real. | ✅ | Mantener esta protección y su prueba. |
| sin asignaciones puede leer y autorizar cualquier paciente | Médico | Denegar lectura y autorización sin asignación médico-paciente. | Brecha reproducida: sin asignaciones puede leer y autorizar cualquier paciente. | ❌ | limitar alcance. |
| no existe representación legal verificable ni rol de tutor | Tutor | Disponer de representación legal verificable para menores. | Brecha reproducida: no existe representación legal verificable ni rol de tutor. | ❌ | no compartir credenciales. |
| quien solo tiene el enlace, sin fecha ni código, no ve el PDF | Paciente | quien solo tiene el enlace, sin fecha ni código, no ve el PDF | Contrato satisfecho en la aplicación real. | ✅ | el error queda auditado. |
| la firma PDF no garantiza documento válido ni legible | Laboratorio | Rechazar contenido inválido aunque comience con firma PDF. | Brecha reproducida: la firma PDF no garantiza documento válido ni legible. | ❌ | validar contenido. |
| la preferencia de entrega asistida se respeta aunque haya correo y teléfono. | EIRA | Respetar la preferencia asistida aunque haya correo y teléfono. | Contrato satisfecho en la aplicación real. | ✅ | Mantener esta protección y su prueba. |
| recorrido HTTP completo y descarga autenticada. | Laboratorio/EIRA/médico/paciente | recorrido HTTP completo y descarga autenticada. | Contrato satisfecho en la aplicación real. | ✅ | Mantener esta protección y su prueba. |
| solicitudes repetidas con fecha correcta generan códigos sin límite | Paciente | Aplicar límite de frecuencia a códigos; contrato propuesto: máximo tres solicitudes consecutivas inmediatas. | Brecha reproducida: solicitudes repetidas con fecha correcta generan códigos sin límite. | ❌ | limitar frecuencia y evitar abuso del canal. |
| reintento de aviso cambia a SMS y revoca el enlace anterior incluso ya verificado. | EIRA | reintento de aviso cambia a SMS y revoca el enlace anterior incluso ya verificado. | Contrato satisfecho en la aplicación real. | ✅ | Mantener esta protección y su prueba. |
| la misma identidad revisora no autoriza aunque cambie de rol. | EIRA/médico | la misma identidad revisora no autoriza aunque cambie de rol. | Contrato satisfecho en la aplicación real. | ✅ | Mantener esta protección y su prueba. |
| no puede autorizar desde cargado. | Médico | no puede autorizar desde cargado. | Contrato satisfecho en la aplicación real. | ✅ | Mantener esta protección y su prueba. |
| sin correo ni teléfono se registra entrega asistida con identidad. | EIRA | sin correo ni teléfono se registra entrega asistida con identidad. | Contrato satisfecho en la aplicación real. | ✅ | Mantener esta protección y su prueba. |
| la ruta interna del personal exige inicio de sesión, no sustituye al enlace de paciente. | Anónimo | la ruta interna del personal exige inicio de sesión, no sustituye al enlace de paciente. | Contrato satisfecho en la aplicación real. | ✅ | Mantener esta protección y su prueba. |
| el enlace del aviso vence a las 72 horas y deja de abrir. | Paciente | El enlace del aviso caduca a las 72 horas. | Contrato satisfecho en la aplicación real. | ✅ | Mantener esta protección y su prueba. |
| falta control de varios pacientes por PDF | EIRA | Exigir control explícito de una sola paciente por documento. | Brecha reproducida: falta control de varios pacientes por PDF. | ❌ | exigir revisión explícita. |
