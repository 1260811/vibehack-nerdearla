# 02 · Diagrama de flujo

Vista de proceso para presentar la propuesta. El detalle técnico con permisos reales está en [diagrama_flujo.md](../diagrama_flujo.md). Las líneas discontinuas son **pendientes**, no funciones existentes.

## Proceso de punta a punta

```mermaid
flowchart TD
  INICIO([Laboratorio tiene el PDF del resultado]) --> CARGA{¿Cómo entrega?}
  CARGA -->|Carga manual| VAL
  CARGA -->|Bandeja: PDF + JSON| JSON{¿JSON válido y folio nuevo?}
  JSON -->|No| RECH[Rechazados + motivo + bitácora]
  JSON -->|Sí| VAL{¿Es PDF y tamaño válido?}
  VAL -->|No| RECH
  VAL -->|Sí| C[Cargado · SHA-256 · almacén privado]

  C --> ID{EIRA: ¿nombre, fecha y folio coinciden con el expediente?}
  ID -->|No| DEV[Devuelto con motivo]
  ID -->|Sí| AS[Asociado]
  AS --> REV{EIRA: ¿legible y de una sola paciente?}
  REV -->|No| DEV
  REV -->|Sí| RV[Revisado]
  RV --> MED{Médico distinto del revisor: ¿autoriza?}
  MED -->|No| DEV
  MED -->|Sí| AU[Autorizado]
  DEV --> CORR[Laboratorio corrige y vuelve a cargar] --> CARGA

  AU --> PREF{¿Prefiere digital y tiene correo o teléfono?}
  PREF -->|No| ASIS[Entrega asistida: receptor + verificación]
  PREF -->|Sí| AV[Aviso sin datos clínicos + enlace 72 h · Notificado]
  AV --> OK{¿El aviso llegó?}
  OK -->|Falló| RE{¿Menos de 2 fallos?}
  RE -->|Sí| AV2[Reintento por el otro canal, enlace anterior invalidado] --> OK
  RE -->|No| ASIS
  OK -->|Sí| PAC[Paciente abre el enlace]
  PAC --> FN{¿Fecha de nacimiento correcta?}
  FN -->|Sí| COD[Código de 6 dígitos por el otro canal · 10 min]
  COD --> VC{¿Código correcto?}
  VC -->|Sí| CONS([Consultado · acuse en bitácora])
  FN -->|No| ERR{¿3 errores?}
  VC -->|No| ERR
  ERR -->|No| PAC
  ERR -->|Sí| BLOQ[Enlace bloqueado] --> ASIS
  ASIS --> FIN([Entregado])
  CONS --> FIN

  AU -.-> TUT[Pendiente: tutor legal]
  CORR -.-> VER[Pendiente: versión y revocación del documento anterior]
```

## Secuencia del acceso de la paciente

```mermaid
sequenceDiagram
  actor M as Médico
  participant S as EIRA (sistema)
  participant N as Proveedor correo/SMS
  actor P as Paciente
  M->>S: Autorizar resultado
  S->>S: Crear enlace (guarda solo SHA-256 del token)
  S->>N: Aviso sin datos clínicos + enlace
  N->>P: Correo o SMS
  P->>S: Abre enlace y escribe fecha de nacimiento
  S->>S: Compara fecha (3 intentos máximo)
  S->>N: Código de 6 dígitos por el otro canal
  N->>P: Código
  P->>S: Escribe código
  S->>S: Valida huella y vigencia (10 min)
  S-->>P: Muestra y permite descargar el PDF
  S->>S: Bitácora: acuse (canales, destino enmascarado, hora, IP)
```

## Estados del documento

```mermaid
stateDiagram-v2
  [*] --> cargado
  cargado --> asociado: EIRA asocia
  asociado --> revisado: EIRA revisa
  revisado --> autorizado: Médico autoriza
  autorizado --> notificado: Aviso enviado
  notificado --> consultado: Paciente verifica
  cargado --> devuelto
  asociado --> devuelto
  revisado --> devuelto
  autorizado --> entregado_asistido
  notificado --> entregado_asistido
  consultado --> [*]
  entregado_asistido --> [*]
  devuelto --> [*]: se carga un documento nuevo
```
