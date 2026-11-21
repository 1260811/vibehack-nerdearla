# Backend (estructura propuesta)

> Sin código todavía. Estructura de referencia para FastAPI + SQLAlchemy, organizada por módulo de dominio.

```
backend/
├── app/
│   ├── main.py              # crea la app FastAPI y registra routers
│   ├── config.py            # configuración por entorno (sin secretos en código)
│   ├── db.py                # motor y sesión de SQLAlchemy
│   ├── seguridad/           # autenticación, hash de contraseñas, permisos por rol
│   ├── bitacora/            # registro de accesos y cambios
│   ├── pacientes/
│   ├── historia_clinica/
│   ├── valoraciones/
│   ├── catalogos/           # padecimientos, zonas, etiquetas, intervenciones
│   ├── sesiones/
│   └── archivos/            # Cloud Storage y URLs firmadas
└── pyproject.toml
```

Cada módulo de dominio sigue la misma forma:

| Archivo | Responsabilidad |
|---|---|
| `models.py` | Modelos SQLAlchemy (reflejan las migraciones, no las crean) |
| `schemas.py` | Esquemas Pydantic de entrada y salida |
| `service.py` | Reglas de negocio y transacciones |
| `router.py` | Endpoints HTTP; solo validan, autorizan y delegan al servicio |

## Lineamientos

- El esquema lo controla **Flyway**; no usar `create_all` de SQLAlchemy en ningún entorno.
- Autorización en cada endpoint mediante dependencias de FastAPI, no en el frontend.
- Las respuestas exponen solo los campos permitidos para el rol.
- Transacciones explícitas en operaciones que tocan varias tablas (p. ej. sesión + padecimientos + intervenciones).
- Conexión a Cloud SQL por conector oficial o IP privada; credenciales desde Secret Manager.
