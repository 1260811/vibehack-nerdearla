"""Reglas de negocio: máquina de estados, verificación de identidad y bitácora."""
import hashlib
import json
import os
import shutil
import tempfile
import time
import unicodedata
from datetime import date, timedelta
from pathlib import Path

from django.conf import settings
from django.core.files import File
from django.db import transaction
from django.db.models import Count
from django.utils import timezone

from .models import Estado, EventoBitacora, Notificacion, Paciente, Resultado, Rol, Usuario


class ReglaNegocioError(Exception):
    pass


# (estado actual, estado nuevo) -> roles que pueden hacer la transición
TRANSICIONES = {
    (Estado.CARGADO, Estado.ASOCIADO): {Rol.EIRA},
    (Estado.CARGADO, Estado.DEVUELTO): {Rol.EIRA},
    (Estado.ASOCIADO, Estado.REVISADO): {Rol.EIRA},
    (Estado.ASOCIADO, Estado.DEVUELTO): {Rol.EIRA},
    (Estado.REVISADO, Estado.AUTORIZADO): {Rol.MEDICO},
    (Estado.REVISADO, Estado.DEVUELTO): {Rol.MEDICO},
    (Estado.AUTORIZADO, Estado.NOTIFICADO): {Rol.EIRA},
    (Estado.AUTORIZADO, Estado.ENTREGADO_ASISTIDO): {Rol.EIRA},
    (Estado.NOTIFICADO, Estado.ENTREGADO_ASISTIDO): {Rol.EIRA},
    (Estado.NOTIFICADO, Estado.CONSULTADO): {Rol.PACIENTE},
}

ESTADOS_VISIBLES_PACIENTE = {Estado.AUTORIZADO, Estado.NOTIFICADO, Estado.CONSULTADO, Estado.ENTREGADO_ASISTIDO}

MENSAJE_AVISO = (
    "Hola {nombre}: tienes un documento disponible en el portal de EIRA. "
    "Inicia sesión con tu usuario para consultarlo. "
    "Por tu seguridad, este mensaje no contiene información clínica."
)


def registrar(usuario, accion, resultado=None, anterior="", nuevo="", detalle=""):
    return EventoBitacora.objects.create(
        usuario=usuario, accion=accion, resultado=resultado,
        estado_anterior=anterior, estado_nuevo=nuevo, detalle=detalle,
    )


def _transicionar(resultado, usuario, nuevo, accion, detalle=""):
    roles = TRANSICIONES.get((resultado.estado, nuevo))
    if roles is None:
        raise ReglaNegocioError(
            f"No se puede pasar de «{Estado(resultado.estado).label}» a «{Estado(nuevo).label}»."
        )
    if usuario.rol not in roles:
        raise ReglaNegocioError("Tu rol no puede realizar esta acción.")
    anterior = resultado.estado
    # Actualización condicional: si otra petición ya cambió el estado, no se sobrescribe.
    if not Resultado.objects.filter(pk=resultado.pk, estado=anterior).update(estado=nuevo):
        raise ReglaNegocioError("El documento cambió mientras trabajabas en él. Recarga la página.")
    resultado.estado = nuevo
    resultado.save()
    registrar(usuario, accion, resultado, anterior, nuevo, detalle)


def normalizar(texto):
    sin_acentos = unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode()
    return " ".join(sin_acentos.lower().split())


def calcular_sha256(archivo):
    h = hashlib.sha256()
    archivo.seek(0)
    for bloque in iter(lambda: archivo.read(64 * 1024), b""):
        h.update(bloque)
    archivo.seek(0)
    return h.hexdigest()


def enmascarar(destino):
    if "@" in destino:
        usuario, dominio = destino.split("@", 1)
        return f"{usuario[:1]}***@{dominio}"
    return "*" * max(len(destino) - 4, 0) + destino[-4:]


# ---------- Carga ----------

@transaction.atomic
def cargar_resultado(usuario, archivo, hoja_nombre, hoja_fecha_nacimiento, hoja_folio_expediente, folio_laboratorio,
                     origen="Carga manual"):
    if usuario.rol not in {Rol.LABORATORIO, Rol.EIRA}:
        raise ReglaNegocioError("Tu rol no puede cargar documentos.")
    if archivo.size > settings.TAMANO_MAXIMO_PDF:
        raise ReglaNegocioError("El archivo supera el tamaño máximo de 10 MB.")
    archivo.seek(0)
    if archivo.read(5) != b"%PDF-":
        raise ReglaNegocioError("Solo se aceptan archivos PDF.")
    sha = calcular_sha256(archivo)
    resultado = Resultado(
        sha256=sha,
        hoja_nombre=hoja_nombre.strip(),
        hoja_fecha_nacimiento=hoja_fecha_nacimiento,
        hoja_folio_expediente=hoja_folio_expediente.strip().upper(),
        folio_laboratorio=folio_laboratorio.strip().upper(),
        cargado_por=usuario,
    )
    resultado.archivo.save("resultado.pdf", archivo, save=False)
    resultado.save()
    registrar(usuario, "Carga de PDF", resultado, "", Estado.CARGADO,
              f"{origen} · Folio de laboratorio {resultado.folio_laboratorio} · SHA-256 {sha[:16]}…")
    return resultado


# ---------- Bandeja de entrada (el laboratorio solo deja archivos en una carpeta) ----------

CAMPOS_HOJA = ("nombre", "fecha_nacimiento", "folio_expediente", "folio_laboratorio")
TAMANO_MAXIMO_JSON = 64 * 1024


def pendientes_en_bandeja(carpeta=None):
    carpeta = Path(carpeta or settings.CARPETA_ENTRADA)
    return sorted(carpeta.glob("*.pdf")) if carpeta.is_dir() else []


def _archivar(destino, *rutas):
    """Mueve los archivos de un envío a `destino` sin pisar envíos anteriores con el mismo nombre."""
    destino.mkdir(parents=True, exist_ok=True)
    sufijo = f"-{timezone.now():%Y%m%d-%H%M%S-%f}" if any((destino / r.name).exists() for r in rutas) else ""
    finales = [destino / f"{r.stem}{sufijo}{r.suffix}" for r in rutas]
    for ruta, final in zip(rutas, finales):
        shutil.move(str(ruta), str(final))
    return finales


def _reclamar(ruta, trabajo):
    """Mueve el archivo a la carpeta privada de esta importación; None si otra ya lo tomó."""
    try:
        os.rename(ruta, trabajo / ruta.name)
    except FileNotFoundError:
        return None
    return trabajo / ruta.name


def _reciente(ruta, ahora):
    try:
        return ahora - ruta.lstat().st_mtime < settings.SEGUNDOS_ESPERA_BANDEJA
    except FileNotFoundError:
        return False


def importar_bandeja(usuario, carpeta=None):
    """Carga cada PDF de la bandeja con los datos de su archivo .json gemelo.

    Usa las mismas validaciones que la carga manual. Los PDFs cargados pasan a
    `procesados/`; los rechazados, a `rechazados/` junto con un .txt con el motivo.
    """
    carpeta = Path(carpeta or settings.CARPETA_ENTRADA)
    cargados, rechazados = [], []
    ahora = time.time()
    trabajo = None
    for pdf in pendientes_en_bandeja(carpeta):
        datos_json = pdf.with_suffix(".json")
        if _reciente(pdf, ahora) or _reciente(datos_json, ahora):
            continue
        trabajo = trabajo or Path(tempfile.mkdtemp(prefix=".importando-", dir=carpeta))
        pdf = _reclamar(pdf, trabajo)
        if pdf is None:
            continue
        datos_json = _reclamar(datos_json, trabajo) or trabajo / datos_json.name
        try:
            if pdf.is_symlink() or datos_json.is_symlink():
                raise ReglaNegocioError("No se aceptan enlaces simbólicos; deja el archivo real en la bandeja.")
            if not datos_json.exists():
                raise ReglaNegocioError(f"Falta {datos_json.name} con los datos de la hoja.")
            if datos_json.stat().st_size > TAMANO_MAXIMO_JSON:
                raise ReglaNegocioError(f"{datos_json.name} es demasiado grande para ser una hoja de datos.")
            try:
                hoja = json.loads(datos_json.read_text(encoding="utf-8"))
                faltan = [c for c in CAMPOS_HOJA if not str(hoja.get(c, "")).strip()]
                fecha = date.fromisoformat(hoja.get("fecha_nacimiento", ""))
            except (ValueError, AttributeError):
                raise ReglaNegocioError(f"{datos_json.name} no es válido (JSON con fecha AAAA-MM-DD).")
            if faltan:
                raise ReglaNegocioError(f"En {datos_json.name} faltan: {', '.join(faltan)}.")
            folio = hoja["folio_laboratorio"].strip().upper()
            if Resultado.objects.filter(folio_laboratorio=folio).exists():
                raise ReglaNegocioError(f"El folio de laboratorio {folio} ya fue cargado.")
            with open(pdf, "rb") as f:
                resultado = cargar_resultado(
                    usuario, File(f, name=pdf.name),
                    hoja_nombre=hoja["nombre"], hoja_fecha_nacimiento=fecha,
                    hoja_folio_expediente=hoja["folio_expediente"], folio_laboratorio=folio,
                    origen=f"Bandeja de entrada ({pdf.name})",
                )
        except ReglaNegocioError as e:
            motivo = str(e)
            registrar(usuario, "Importación rechazada", detalle=f"{pdf.name}: {motivo}")
            enviados = [pdf] + ([datos_json] if datos_json.exists() or datos_json.is_symlink() else [])
            archivado = _archivar(carpeta / "rechazados", *enviados)[0]
            (carpeta / "rechazados" / f"{archivado.stem}.motivo.txt").write_text(motivo + "\n", encoding="utf-8")
            rechazados.append((pdf.name, motivo))
        else:
            _archivar(carpeta / "procesados", pdf, datos_json)
            cargados.append(resultado)
    if trabajo:
        trabajo.rmdir()
    return cargados, rechazados


# ---------- Asociación con verificación de identidad ----------

def comparar_identidad(resultado, paciente):
    filas = [
        ("Nombre", resultado.hoja_nombre, paciente.nombre,
         normalizar(resultado.hoja_nombre) == normalizar(paciente.nombre)),
        ("Fecha de nacimiento", resultado.hoja_fecha_nacimiento, paciente.fecha_nacimiento,
         resultado.hoja_fecha_nacimiento == paciente.fecha_nacimiento),
        ("Folio de expediente", resultado.hoja_folio_expediente, paciente.folio_expediente,
         normalizar(resultado.hoja_folio_expediente) == normalizar(paciente.folio_expediente)),
    ]
    return [{"campo": c, "hoja": h, "expediente": e, "coincide": ok} for c, h, e, ok in filas]


def candidatos(resultado):
    """Expedientes que coinciden en al menos un dato, para que EIRA compare."""
    salida = []
    for paciente in Paciente.objects.order_by("nombre", "fecha_nacimiento"):
        comparacion = comparar_identidad(resultado, paciente)
        if any(f["coincide"] for f in comparacion):
            salida.append({
                "paciente": paciente,
                "comparacion": comparacion,
                "coincide_todo": all(f["coincide"] for f in comparacion),
            })
    return sorted(salida, key=lambda c: -sum(f["coincide"] for f in c["comparacion"]))


def asociar(resultado, paciente, usuario):
    comparacion = comparar_identidad(resultado, paciente)
    fallas = [f["campo"] for f in comparacion if not f["coincide"]]
    if fallas:
        registrar(usuario, "Asociación bloqueada", resultado,
                  detalle=f"Expediente {paciente.folio_expediente}: no coincide {', '.join(fallas).lower()}.")
        raise ReglaNegocioError(
            f"No se puede asociar: no coincide {', '.join(fallas).lower()}. Verifica los datos o devuelve el documento."
        )
    with transaction.atomic():
        resultado.paciente = paciente
        resultado.asociado_por = usuario
        _transicionar(resultado, usuario, Estado.ASOCIADO, "Asociación con expediente",
                      f"Expediente {paciente.folio_expediente}: coinciden nombre, fecha de nacimiento y folio.")


# ---------- Revisión, autorización y devolución ----------

@transaction.atomic
def aprobar_revision(resultado, usuario):
    resultado.revisado_por = usuario
    _transicionar(resultado, usuario, Estado.REVISADO, "Revisión administrativa aprobada",
                  "Documento legible y datos verificados.")


@transaction.atomic
def devolver(resultado, usuario, motivo):
    motivo = (motivo or "").strip()
    if not motivo:
        raise ReglaNegocioError("Para devolver un documento debes indicar el motivo.")
    resultado.motivo_devolucion = motivo
    _transicionar(resultado, usuario, Estado.DEVUELTO, "Documento devuelto", motivo)


@transaction.atomic
def autorizar(resultado, usuario, requiere_contacto=False):
    if resultado.revisado_por_id == usuario.id:
        raise ReglaNegocioError("Quien hizo la revisión administrativa no puede autorizar clínicamente.")
    resultado.autorizado_por = usuario
    resultado.requiere_contacto = requiere_contacto
    _transicionar(resultado, usuario, Estado.AUTORIZADO, "Autorización clínica",
                  "Requiere contacto con la paciente." if requiere_contacto else "Sin indicaciones adicionales.")


# ---------- Entrega ----------

def tiene_acceso_digital(paciente):
    return Usuario.objects.filter(paciente=paciente, is_active=True).exists()


@transaction.atomic
def notificar(resultado, usuario, canal):
    paciente = resultado.paciente
    if paciente is None:
        raise ReglaNegocioError("El documento no está asociado a una paciente.")
    if not tiene_acceso_digital(paciente):
        raise ReglaNegocioError("La paciente no tiene acceso al portal: registra una entrega asistida.")
    destino = paciente.correo if canal == Notificacion.Canal.CORREO else paciente.telefono
    if not destino:
        raise ReglaNegocioError(f"La paciente no tiene {Notificacion.Canal(canal).label.lower()} registrado.")
    Notificacion.objects.create(
        resultado=resultado, canal=canal, destino=destino,
        mensaje=MENSAJE_AVISO.format(nombre=paciente.nombre.split()[0]),
    )
    _transicionar(resultado, usuario, Estado.NOTIFICADO,
                  f"Aviso simulado por {Notificacion.Canal(canal).label.lower()}", f"Destino: {enmascarar(destino)}")


@transaction.atomic
def registrar_entrega_asistida(resultado, usuario, receptor, verificacion):
    receptor, verificacion = (receptor or "").strip(), (verificacion or "").strip()
    if not receptor or not verificacion:
        raise ReglaNegocioError("Indica quién recibió el documento y cómo se verificó su identidad.")
    detalle = f"Recibió: {receptor}. Identidad verificada con: {verificacion}."
    resultado.entrega_asistida_detalle = detalle
    _transicionar(resultado, usuario, Estado.ENTREGADO_ASISTIDO, "Entrega asistida", detalle)


# ---------- Acceso al documento ----------

def puede_ver_documento(usuario, resultado):
    if usuario.rol in {Rol.EIRA, Rol.MEDICO}:
        return True
    if usuario.rol == Rol.LABORATORIO:
        return resultado.cargado_por_id == usuario.id
    if usuario.rol == Rol.PACIENTE:
        return (
            usuario.paciente_id is not None
            and resultado.paciente_id == usuario.paciente_id
            and resultado.estado in ESTADOS_VISIBLES_PACIENTE
        )
    return False


def integridad_correcta(resultado):
    with resultado.archivo.open("rb") as f:
        return calcular_sha256(f) == resultado.sha256


@transaction.atomic
def registrar_acceso(usuario, resultado, descarga=False):
    accion = "Descarga del documento" if descarga else "Visualización del documento"
    if usuario.rol == Rol.PACIENTE and resultado.estado == Estado.NOTIFICADO:
        try:
            _transicionar(resultado, usuario, Estado.CONSULTADO, "Consulta por la paciente", accion)
            return
        except ReglaNegocioError:
            resultado.refresh_from_db()
    registrar(usuario, accion, resultado)


# ---------- Panel de seguimiento ----------

# (clave, etiqueta, a quién le toca, estados que agrupa)
ETAPAS = [
    ("por_asociar", "Por asociar", "EIRA", [Estado.CARGADO]),
    ("en_revision", "En revisión", "EIRA", [Estado.ASOCIADO]),
    ("por_autorizar", "Por autorizar", "Médico", [Estado.REVISADO]),
    ("por_entregar", "Listos para entregar", "EIRA", [Estado.AUTORIZADO]),
    ("sin_consultar", "Avisados sin consultar", "Paciente", [Estado.NOTIFICADO]),
    ("entregados", "Entregados", "Completado", [Estado.CONSULTADO, Estado.ENTREGADO_ASISTIDO]),
    ("devueltos", "Devueltos", "Laboratorio", [Estado.DEVUELTO]),
]
ESTADOS_ENTREGADOS = {Estado.CONSULTADO, Estado.ENTREGADO_ASISTIDO}
ESTADOS_CERRADOS = ESTADOS_ENTREGADOS | {Estado.DEVUELTO}


def estados_de_etapa(clave):
    return next((estados for c, _, _, estados in ETAPAS if c == clave), None)


def formato_duracion(delta):
    minutos = int(delta.total_seconds() // 60)
    if minutos < 60:
        return f"{minutos} min"
    horas, minutos = divmod(minutos, 60)
    if horas < 24:
        return f"{horas} h {minutos} min"
    dias, horas = divmod(horas, 24)
    return f"{dias} d {horas} h"


def indicadores_panel():
    conteos = dict(Resultado.objects.values_list("estado").annotate(n=Count("id")))
    total = sum(conteos.values())
    etapas = []
    for clave, etiqueta, responsable, estados in ETAPAS:
        n = sum(conteos.get(e.value, 0) for e in estados)
        etapas.append({
            "clave": clave, "etiqueta": etiqueta, "responsable": responsable, "n": n,
            "porcentaje": round(100 * n / total) if total else 0,
        })

    entregados = Resultado.objects.filter(estado__in=ESTADOS_ENTREGADOS)
    duraciones = []
    for r in entregados.prefetch_related("eventos"):
        fin = min((e.fecha for e in r.eventos.all() if e.estado_nuevo in ESTADOS_ENTREGADOS), default=None)
        if fin:
            duraciones.append(fin - r.creado)
    limite = timezone.now() - timedelta(hours=settings.HORAS_DOCUMENTO_DETENIDO)
    return {
        "total": total,
        "etapas": etapas,
        "entregados": entregados.count(),
        "porcentaje_entregado": round(100 * entregados.count() / total) if total else 0,
        "tiempo_promedio": formato_duracion(sum(duraciones, timedelta()) / len(duraciones)) if duraciones else "—",
        "en_proceso": Resultado.objects.exclude(estado__in=ESTADOS_CERRADOS).count(),
        "detenidos": Resultado.objects.exclude(estado__in=ESTADOS_CERRADOS).filter(actualizado__lt=limite).count(),
        "horas_detenido": settings.HORAS_DOCUMENTO_DETENIDO,
        "requieren_contacto": Resultado.objects.filter(requiere_contacto=True).exclude(
            estado__in=[Estado.ENTREGADO_ASISTIDO, Estado.DEVUELTO]).count(),
    }
