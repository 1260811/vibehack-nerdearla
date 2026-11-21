# Datos sintéticos — Entrega segura de resultados de Papanicolaou (EIRA)

Todos los datos son ficticios. Los correos usan el dominio reservado `.test`.

## Contenido
- `pacientes.json`: 4 expedientes ficticios.
- `usuarios.json`: un usuario por rol más 3 pacientes con acceso digital. Contraseña de demo: `Demo2026!`.
- `resultados.json`: metadatos de cada PDF (datos impresos en la hoja, escenario, paciente esperada, hash SHA-256).
- `pdfs/`: 5 reportes con aspecto de escaneo y marca de agua "DOCUMENTO SINTÉTICO".
- `herramientas/generar.py`: regenera todo (`pip install reportlab pillow pymupdf`).

## Escenarios de demostración
| PDF | Escenario | Resultado esperado |
|---|---|---|
| R1 | Flujo feliz (P1, normal) | Se asocia, se revisa, se autoriza, se notifica y la paciente lo consulta |
| R2 | Homónima (mismo nombre que P1) | Solo se asocia con P2 por fecha y folio; el médico marca "requiere contacto" (LSIL) |
| R3 | P3 sin correo ni usuario | Entrega asistida registrada por EIRA |
| R4 | Datos que no coinciden | La asociación se bloquea |
| R5 | Escaneo ilegible | EIRA lo devuelve en la revisión con un motivo |
