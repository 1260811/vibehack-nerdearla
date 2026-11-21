# 06 · Archivos e imagenología

## Reglas

- Los binarios se guardan en **Cloud Storage**, nunca en la base de datos.
- Bucket **privado**: sin acceso público, con acceso uniforme a nivel de bucket.
- La BD guarda la **referencia** (`bucket`, `object_key`), nunca una URL pública permanente.
- El backend genera **URLs firmadas de corta duración** solo para usuarios autorizados y registra el acceso.
- `object_key` no adivinable y sin datos personales (p. ej. `pacientes/{paciente_id}/{uuid}`).
- Validar tipo MIME y tamaño máximo al subir.

## Metadatos a registrar

| Campo | Notas |
|---|---|
| `paciente_id` | Obligatorio |
| `sesion_clinica_id` | Opcional: el archivo puede ser del expediente o de una sesión |
| `tipo_archivo_id` | Fotografía, radiografía, resonancia, ultrasonido, PDF, otro |
| `nombre_original` | Solo para mostrar |
| `bucket`, `object_key` | Ubicación del objeto |
| `mime_type`, `tamano_bytes` | Validados al subir |
| `descripcion` | Opcional |
| `usuario_id`, `created_at` | Quién y cuándo lo subió |

## A definir

- Retención de objetos y relación con el plazo de conservación del expediente.
- Versionado de objetos o bloqueo de retención para evitar borrados accidentales.
- Clase de almacenamiento según frecuencia de acceso.
