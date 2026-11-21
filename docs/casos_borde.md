# Casos de borde del flujo real

Generado con `python3 manage.py probar_flujo` sobre una base aislada de pruebas.

✅ = contrato satisfecho; ❌ = brecha reproducida (fallo esperado), no una protección implementada.
Los contratos de funciones/campos ausentes comprueban ausencia, no simulan una implementación.
No se probaron proveedores reales, OCR, conectividad ni despliegue productivo.

Escenarios: 29. Brechas esperadas: 14. Fallos inesperados: 0.

| Escenario | Actor | Esperado | Obtenido | Estado | Riesgo/recomendación |
|---|---|---|---|---|---|
| plantilla alterada admite diagnóstico sin filtro | EIRA | Rechazar cualquier aviso con diagnóstico o hallazgos. | Brecha reproducida: plantilla alterada admite diagnóstico sin filtro. | ❌ | validar antes de guardar. |
| aviso predeterminado no revela hallazgos ni diagnóstico. | EIRA | aviso predeterminado no revela hallazgos ni diagnóstico. | Contrato satisfecho en la aplicación real. | ✅ | Mantener esta protección y su prueba. |
| bandeja bloquea folio previamente cargado, a diferencia de carga manual. | Laboratorio | bandeja bloquea folio previamente cargado, a diferencia de carga manual. | Contrato satisfecho en la aplicación real. | ✅ | Mantener esta protección y su prueba. |
| PDF sin datos se rechaza, archiva y audita. | Laboratorio | PDF sin datos se rechaza, archiva y audita. | Contrato satisfecho en la aplicación real. | ✅ | Mantener esta protección y su prueba. |
| bandeja vacía no genera documentos ni rechazos. | Laboratorio | bandeja vacía no genera documentos ni rechazos. | Contrato satisfecho en la aplicación real. | ✅ | Mantener esta protección y su prueba. |
| QuerySet.update evita save y altera bitácora | Sistema | Impedir cambios de bitácora también mediante ORM masivo. | Brecha reproducida: QuerySet.update evita save y altera bitácora. | ❌ | proteger en base de datos. |
| modificar o borrar una instancia de bitácora está bloqueado. | EIRA | modificar o borrar una instancia de bitácora está bloqueado. | Contrato satisfecho en la aplicación real. | ✅ | Mantener esta protección y su prueba. |
| cargador con cambio de rol puede autorizar | Médico | Impedir que la identidad cargadora autorice clínicamente. | Brecha reproducida: cargador con cambio de rol puede autorizar. | ❌ | separar carga y autorización. |
| no existe versión/revocación ni reaviso | EIRA | Ofrecer corrección versionada, reaviso y revocación de la versión anterior. | Brecha reproducida: no existe versión/revocación ni reaviso. | ❌ | impedir acceso a versión anterior. |
| saltos de estado denegados no dejan evento | Médico | Registrar un evento incluso cuando se rechaza una transición. | Brecha reproducida: saltos de estado denegados no dejan evento. | ❌ | auditar todos los rechazos. |
| carga manual repite hash y folio | Laboratorio | Rechazar una segunda carga del mismo documento/folio. | Brecha reproducida: carga manual repite hash y folio. | ❌ | deduplicar también fuera de bandeja. |
| una URL autenticada puede descargarse repetidamente | Paciente | Rechazar la reutilización de una descarga consumida. | Brecha reproducida: una URL autenticada puede descargarse repetidamente. | ❌ | falta uso único. |
| no hay proveedor ni falla/fallback correo→SMS→asistida | Sistema | Ofrecer respaldo ante falla de correo, después SMS y finalmente asistencia. | Brecha reproducida: no hay proveedor ni falla/fallback correo→SMS→asistida. | ❌ | solo simulación. |
| homónimos con fecha y expediente diferentes no se confunden. | EIRA | homónimos con fecha y expediente diferentes no se confunden. | Contrato satisfecho en la aplicación real. | ✅ | Mantener esta protección y su prueba. |
| un folio discrepante bloquea y audita la asociación. | EIRA | un folio discrepante bloquea y audita la asociación. | Contrato satisfecho en la aplicación real. | ✅ | Mantener esta protección y su prueba. |
| revisión humana devuelve escaneo ilegible con motivo. | EIRA | revisión humana devuelve escaneo ilegible con motivo. | Contrato satisfecho en la aplicación real. | ✅ | Mantener esta protección y su prueba. |
| otro usuario de laboratorio no puede acceder al documento. | Laboratorio | otro usuario de laboratorio no puede acceder al documento. | Contrato satisfecho en la aplicación real. | ✅ | Mantener esta protección y su prueba. |
| sin asignaciones puede leer y autorizar cualquier paciente | Médico | Denegar lectura y autorización sin asignación médico-paciente. | Brecha reproducida: sin asignaciones puede leer y autorizar cualquier paciente. | ❌ | limitar alcance. |
| no existe representación legal verificable ni rol de tutor | Tutor | Disponer de representación legal verificable para menores. | Brecha reproducida: no existe representación legal verificable ni rol de tutor. | ❌ | no compartir credenciales. |
| documento ajeno responde 404 y deja auditoría de acceso denegado. | Paciente | documento ajeno responde 404 y deja auditoría de acceso denegado. | Contrato satisfecho en la aplicación real. | ✅ | Mantener esta protección y su prueba. |
| la firma PDF no garantiza documento válido ni legible | Laboratorio | Rechazar contenido inválido aunque comience con firma PDF. | Brecha reproducida: la firma PDF no garantiza documento válido ni legible. | ❌ | validar contenido. |
| preferencia asistida con cuenta activa no bloquea aviso digital | EIRA | Respetar la preferencia asistida aunque exista una cuenta activa. | Brecha reproducida: preferencia asistida con cuenta activa no bloquea aviso digital. | ❌ | respetar elección. |
| recorrido HTTP completo y descarga autenticada. | Laboratorio/EIRA/médico/paciente | recorrido HTTP completo y descarga autenticada. | Contrato satisfecho en la aplicación real. | ✅ | Mantener esta protección y su prueba. |
| la misma identidad revisora no autoriza aunque cambie de rol. | EIRA/médico | la misma identidad revisora no autoriza aunque cambie de rol. | Contrato satisfecho en la aplicación real. | ✅ | Mantener esta protección y su prueba. |
| no puede autorizar desde cargado. | Médico | no puede autorizar desde cargado. | Contrato satisfecho en la aplicación real. | ✅ | Mantener esta protección y su prueba. |
| sin correo, teléfono ni cuenta activa se registra entrega asistida con identidad. | EIRA | sin correo, teléfono ni cuenta activa se registra entrega asistida con identidad. | Contrato satisfecho en la aplicación real. | ✅ | Mantener esta protección y su prueba. |
| el enlace exige sesión y no entrega un PDF público. | Anónimo | el enlace exige sesión y no entrega un PDF público. | Contrato satisfecho en la aplicación real. | ✅ | Mantener esta protección y su prueba. |
| no existe token con vencimiento por descarga | Paciente | Emitir tokens de descarga con caducidad independiente de la sesión. | Brecha reproducida: no existe token con vencimiento por descarga. | ❌ | solo sesión de 30 minutos. |
| falta control de varios pacientes por PDF | EIRA | Exigir control explícito de una sola paciente por documento. | Brecha reproducida: falta control de varios pacientes por PDF. | ❌ | exigir revisión explícita. |
