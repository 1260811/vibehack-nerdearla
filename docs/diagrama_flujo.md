# Flujo de entrega: implementación y límites

Fuente: `resultados/models.py`, `servicios.TRANSICIONES`, `puede_ver_documento` y decoradores de `views.py`.
Los identificadores de estado son los reales. Las líneas discontinuas indican tareas pendientes, **no funciones existentes**.
El PNG equivalente se genera con Graphviz: `dot -Tpng docs/diagrama_flujo.dot -o docs/diagrama_flujo.png`.
Se usó Graphviz porque no hay Node/npx en el entorno. No se añadieron dependencias a la aplicación.

```mermaid
flowchart TB
  subgraph lab[Laboratorio]
    L[Subir PDF y datos de la hoja]
    B[Depositar PDF y JSON en bandeja]
    D[devuelto: corregir y cargar otro documento]
  end
  subgraph sistema[Sistema: servicios internos, sin rol de usuario]
    V{Firma PDF y tamaño válidos?}
    J{JSON válido y folio no repetido?}
    R[Rechazo y archivo en rechazados; bitácora]
    C[cargado]
    I{Nombre, fecha y folio coinciden?}
    X[Bloquear asociación y auditar]
    A[Verificar enlace vigente, sesión verificada y SHA-256]
    Q{Acceso e integridad válidos?}
    F[404 por enlace inválido; 409 e incidente si falla integridad]
  end
  subgraph eira[EIRA: captura y revisión en un mismo rol]
    AS[asociado]
    E{Revisión humana: legible y una paciente?}
    RE[revisado]
    N{Prefiere digital y tiene contacto?}
    NO[notificado: aviso correo o SMS simulado]
    RI[Simular falla y reintentar otro canal: revocar enlace anterior]
    RF{Dos fallas de aviso?}
    EA[entregado_asistido: receptor e identidad documentados]
  end
  subgraph medico[Médico: sin asignación individual implementada]
    M{Autorizar o devolver? Revisor distinto?}
    AU[autorizado: sistema decide aviso o asistencia]
  end
  subgraph paciente[Paciente]
    P[Abrir enlace único del aviso: vence en 72 horas]
    FE{Fecha de nacimiento correcta?}
    CD[Recibir código aparte: otro canal si existe]
    VC{Código correcto y vigente: 10 minutos?}
    ER[Error de verificación: contar intento y auditar]
    BL{Tres intentos fallidos?}
    BA[Bloquear enlace y pedir asistencia]
    VE[Sesión verificada por 30 minutos y acuse]
    CO[consultado: solo si antes estaba notificado]
  end
  subgraph pendientes[No implementado: tutor y controles adicionales]
    T[Tutor legal; versiones y revocación; descarga de un uso]
    NC[Falla real correo → SMS → asistencia: pendiente]
  end
  L --> V
  B --> J
  J -->|No| R
  J -->|Sí| V
  V -->|No| R
  V -->|Sí| C
  C --> I
  I -->|No: homónimo o discrepancia| X
  X -->|Verificar expediente correcto| I
  X -->|Devolver con motivo| D
  I -->|Sí| AS
  AS --> E
  E -->|No: ilegible o varias pacientes| D
  E -->|Sí| RE
  RE --> M
  M -->|Devolver con motivo| D
  M -->|Autorizar| AU
  D --> L
  AU --> N
  N -->|Sí: aviso automático al autorizar| NO
  N -->|Prefiere asistida o sin contacto| EA
  NO -->|Alternativa manual| EA
  NO -->|Falla simulada| RI
  RI --> RF
  RF -->|No: nuevo aviso| NO
  RF -->|Sí: gestionar asistencia| EA
  NO --> P
  P -->|Caducado o bloqueado| F
  P -->|Vigente| FE
  FE -->|Sí| CD
  FE -->|No: fecha válida pero incorrecta| ER
  CD --> VC
  VC -->|Sí| VE
  VC -->|Incorrecto| ER
  VC -->|Caducado| FE
  ER --> BL
  BL -->|Sí| BA
  BL -->|No| FE
  BA --> EA
  VE --> A
  A --> Q
  Q -->|No| F
  Q -->|Sí: desde notificado| CO
  NO -.-> NC
  AU -.-> T
```

![Diagrama del flujo real](diagrama_flujo.png)

## Matriz de permisos observados (no matriz ideal)

| Acción | Laboratorio | EIRA | Médico | Paciente | Tutor | Sistema |
|---|---|---|---|---|---|---|
| Cargar PDF / importar bandeja | Sí | Sí | No | No | Ausente | Importador con usuario laboratorio/EIRA |
| Asociar identidad | No | Cargado→asociado | No | No | Ausente | Compara nombre + fecha + folio |
| Revisión administrativa | No | Asociado→revisado | No | No | Ausente | Valida transición |
| Autorizar clínicamente | No | No | Revisado→autorizado, distinto del revisor | No | Ausente | No comprueba asignaciones ni cargador |
| Devolver con motivo | No | Desde cargado/asociado | Desde revisado | No | Ausente | Devuelto no tiene transición de salida |
| Notificar correo/SMS | No | Simular falla y reintentar aviso fallido | Autorizar dispara aviso | No | Ausente | Automático desde autorizado; respaldo simulado a otro canal y asistencia tras dos fallas |
| Registrar entrega asistida | No | Desde autorizado/notificado | No | No | Ausente | Exige receptor y verificación no vacíos |
| Leer/descargar PDF | Solo cargas propias del usuario | Todos, incluso sin autorizar | Todos, incluso sin autorizar | Sin cuenta: enlace del aviso + fecha de nacimiento + código; solo ese resultado | Ausente | Comprueba sesión o enlace verificado, caducidad e integridad |
| Panel, detalle, avisos y bitácora | No | Todos | Todos | No | Ausente | Audita descargas y algunos rechazos |
| Modificar/borrar bitácora | No por instancia | No por instancia | No por instancia | No por instancia | Ausente | ORM masivo puede alterar: brecha |

## Advertencias para la demostración

- No hay roles separados de captura y revisión EIRA, laboratorio como entidad, tutor ni asignación médico-paciente.
- El alcance del laboratorio se limita al **usuario cargador**, no a una organización de laboratorio.
- Ilegibilidad y varias pacientes dependen de revisión humana; la firma `%PDF-` no valida contenido.
- Una devolución obliga a una nueva carga independiente: no hay vínculo de versiones, corrección ni anulación de la anterior.
- No hay estado pendiente de identidad ni rechazado separado: el documento permanece cargado o se devuelve.
- Los avisos son plantillas fijas simuladas: no se prueba entrega real. La paciente entra por enlace (72 h) con fecha de nacimiento y código; 3 errores bloquean el enlace. El aviso se envía al autorizar; el reintento usa otro canal y tras 2 fallos queda entrega asistida.
- Tras verificar, el PDF puede volver a descargarse durante la sesión de 30 minutos: no es de un solo uso.
- El aviso y el código se envían por separado; se prefiere otro canal para el código, pero con un solo contacto se reutiliza ese canal.
- No se emiten enlaces antes de autorizar. La verificación de una paciente no habilita el enlace de otra.
- Cada reintento de aviso revoca el enlace previo; la entrega asistida también revoca enlaces vigentes.
- Las fechas malformadas no cuentan como intento; solicitar códigos con fecha correcta no tiene límite de frecuencia (nuevas brechas).
- `expectedFailure` mantiene la suite ejecutable, pero cada ❌ del informe es un contrato de seguridad incumplido, no una validación aprobada.
