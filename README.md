# EIRA · Entrega segura de resultados de Papanicolaou

Prototipo de hackathon (Nerdearla Vibehack). Reemplaza el flujo "escanear → buscar teléfono → enviar por WhatsApp" por un recorrido controlado, con verificación de identidad, autorización clínica, acceso autenticado y bitácora.

> Todos los datos son sintéticos. No hay integraciones reales: los avisos por correo/SMS se muestran en una bandeja simulada.

## Cómo ejecutarlo

```bash
pip install -r requirements.txt
python manage.py migrate
python manage.py cargar_demo --con-resultados   # pacientes, usuarios y 5 PDFs de ejemplo
python manage.py runserver
```

Abre http://localhost:8000. Contraseña para todos los usuarios: `Demo2026!`

| Rol | Correo | Qué puede hacer |
|---|---|---|
| Laboratorio | `laboratorio@lab.test` | Cargar PDFs y ver el estado de sus cargas |
| EIRA | `admin@eira.test` | Asociar con expediente, revisar, devolver, avisar, registrar entrega asistida, ver panel y bitácora |
| Médico | `medico@eira.test` | Autorizar o devolver; marcar "requiere contacto" |
| Paciente P1 | `maria.lopez.88@ejemplo.test` | Ver y descargar solo sus resultados autorizados |
| Paciente P2 (homónima) | `maria.lopez.92@ejemplo.test` | Igual que P1 |
| Paciente P4 | `ana.ramirez@ejemplo.test` | Igual que P1 |

Sin `--con-resultados`, el laboratorio sube los PDFs a mano desde `datos_demo/pdfs/` (los datos de cada hoja están en `datos_demo/resultados.json`).

## Bandeja de entrada (el laboratorio solo deja archivos)

El laboratorio no tiene que capturar ni avisar: deja cada PDF con un `.json` del mismo nombre en una carpeta compartida y el sistema lo carga con las mismas validaciones que la carga manual.

```
bandeja_entrada/
  R1_LAB-24001.pdf
  R1_LAB-24001.json   {"nombre": "...", "fecha_nacimiento": "1988-03-14", "folio_expediente": "EIRA-0001", "folio_laboratorio": "LAB-24001"}
```

```bash
python manage.py cargar_demo --a-bandeja          # copia los 5 PDFs de ejemplo a la bandeja, como lo haría el laboratorio
python manage.py importar_bandeja                 # los carga (o botón "Importar bandeja ahora" en la pantalla de carga)
python manage.py importar_bandeja --vigilar 30    # revisa la carpeta cada 30 s
```

- Un archivo modificado hace menos de `EIRA_SEGUNDOS_ESPERA_BANDEJA` segundos (por defecto 5) se deja para la siguiente revisión, por si todavía se está copiando.
- Los cargados pasan a `procesados/`; los rechazados (sin `.json`, datos incompletos, folio repetido, no es PDF) a `rechazados/` con un `.motivo.txt`. Todo queda en la bitácora.
- La carpeta se cambia con `EIRA_CARPETA_ENTRADA` (puede ser una carpeta de red o sincronizada con Drive/OneDrive/un bucket). La carga se firma con el usuario `EIRA_USUARIO_BANDEJA` (por defecto `laboratorio@lab.test`).
- Almacenamiento: los PDFs se guardan en `almacen_privado/`. Para pasar a la nube (S3, GCS, Azure) basta configurar `STORAGES` con django-storages; las vistas no cambian.

## Panel de seguimiento

- Indicadores: documentos recibidos, en proceso, % entregados, tiempo promedio de carga a entrega, detenidos más de 24 h y pacientes que requieren contacto.
- Barra y tarjetas por etapa, con a quién le toca: Por asociar (EIRA), En revisión (EIRA), Por autorizar (Médico), Listos para entregar (EIRA), Avisados sin consultar (Paciente), Entregados, Devueltos (Laboratorio). Cada tarjeta filtra la tabla.
- La tabla muestra el avance de cada documento en 6 pasos, a quién le toca y cuánto lleva en la etapa actual.

## Recorrido del documento

```
Cargado → Asociado → Revisado → Autorizado → Notificado → Consultado
   └──────────┴──────────┴──→ Devuelto (con motivo)
                         Autorizado/Notificado → Entrega asistida
```

## Guion de demostración (escenarios incluidos)

| PDF | Escenario | Qué se demuestra |
|---|---|---|
| LAB-24001 | Flujo feliz (P1) | Asociar → revisar → autorizar → aviso → la paciente lo consulta |
| LAB-24002 | Homónima | Hay dos "María López Hernández": solo se puede asociar con P2 (fecha y folio coinciden). Resultado LSIL: el médico marca "requiere contacto" |
| LAB-24003 | Sin acceso digital (P3) | No se puede avisar; se registra entrega asistida |
| LAB-24004 | Datos que no coinciden | La asociación se bloquea y queda en la bitácora |
| LAB-24005 | Escaneo ilegible | EIRA lo devuelve con motivo |

## Reglas implementadas

- Solo se asocia si coinciden nombre, fecha de nacimiento y folio de expediente (sin importar acentos ni mayúsculas).
- Los estados avanzan en orden y cada transición está limitada a un rol (`resultados/servicios.py`, `TRANSICIONES`).
- Quien revisó no puede autorizar. Devolver exige motivo.
- La paciente solo ve sus documentos autorizados; para cualquier otro recibe 404 (no se revela que existe).
- El aviso no contiene información clínica; el destino se enmascara en la bitácora.
- Los PDFs se guardan con nombre aleatorio en `almacen_privado/`, que ninguna URL expone; solo la vista `documento` los entrega, tras verificar permisos y la huella SHA-256.
- Solo se aceptan PDFs (se valida la firma `%PDF-`) de hasta 10 MB.
- La bitácora es de solo inserción y registra cargas, transiciones, visualizaciones, descargas y accesos denegados.

## Estructura

- `resultados/models.py`: `Paciente`, `Usuario` (con rol), `Resultado`, `Notificacion`, `EventoBitacora`.
- `resultados/servicios.py`: reglas de negocio (máquina de estados, verificación de identidad, bitácora).
- `resultados/views.py`: vistas por rol, descarga protegida, panel, avisos y bitácora.
- `datos_demo/`: datos sintéticos y el script que genera los PDFs.

## Pruebas

```bash
python manage.py test resultados
```

### Tester del flujo real y brechas conocidas

```bash
python3 manage.py test resultados
python3 manage.py probar_flujo
```

El segundo comando ejecuta `resultados/tests_flujo.py` con base de datos aislada y
regenera [casos de borde](docs/casos_borde.md). No modifica los expedientes de la demo.
Los fallos esperados (`expectedFailure`) documentan brechas **sin corregir la aplicación**:
una suite verde no significa que estos controles ya existan. Un éxito inesperado exige
revisar el contrato y retirar la marca si la brecha se resolvió.

- [Flujo Mermaid y matriz de permisos reales](docs/diagrama_flujo.md).
- [Diagrama renderizado PNG](docs/diagrama_flujo.png).
- Fuente alternativa reproducible: `dot -Tpng docs/diagrama_flujo.dot -o docs/diagrama_flujo.png` (Graphviz, solo documentación).

No se añadieron dependencias Python: se utiliza el Django existente y la biblioteca estándar.
Los avisos, asignaciones médicas, representación legal, correcciones versionadas y respaldo
de canales deben revisarse contra el informe antes de considerar un uso real con datos clínicos.
