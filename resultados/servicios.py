"""Reglas de negocio: máquina de estados, verificación de identidad y bitácora."""
import hashlib
import json
import logging
import os
import shutil
import tempfile
import time
import unicodedata
from datetime import date
from pathlib import Path

from django.conf import settings
from django.core.files import File
from django.db import transaction
from django.utils import timezone

from .models import Estado, EventoBitacora, Notificacion, Paciente, Resultado, Rol, Usuario

logger = logging.getLogger(__name__)


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
    (Estado.AUTORIZADO, Estado.NOTIFICADO): set(),  # solo el sistema, al autorizar
    (Estado.AUTORIZADO, Estado.ENTREGADO_ASISTIDO): {Rol.EIRA},
    (Estado.NOTIFICADO, Estado.ENTREGADO_ASISTIDO): {Rol.EIRA},
    (Estado.NOTIFICADO, Estado.CONSULTADO): {Rol.PACIENTE},
}

MAX_FALLOS_AVISO = 2

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


def _transicionar(resultado, usuario, nuevo, accion, detalle="", sistema=False):
    roles = TRANSICIONES.get((resultado.estado, nuevo))
    if roles is None:
        raise ReglaNegocioError(
            f"No se puede pasar de «{Estado(resultado.estado).label}» a «{Estado(nuevo).label}»."
        )
    if not sistema and usuario.rol not in roles:
        raise ReglaNegocioError("Tu rol no puede realizar esta acción.")
    anterior = resultado.estado
    # Actualización condicional: si otra petición ya cambió el estado, no se sobrescribe.
    if not Resultado.objects.filter(pk=resultado.pk, estado=anterior).update(estado=nuevo):
        raise ReglaNegocioError("El documento cambió mientras trabajabas en él. Recarga la página.")
    ahora = timezone.now()
    resultado.estado = nuevo
    resultado.etapa_desde = ahora
    if nuevo == Estado.AUTORIZADO:
        resultado.autorizado_en = ahora
    if nuevo in {Estado.CONSULTADO, Estado.ENTREGADO_ASISTIDO}:
        resultado.entregado_en = ahora
    resultado.save()
    registrar(None if sistema else usuario, accion, resultado, anterior, nuevo, detalle)


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
                faltan = [c for c in CAMPOS_HOJA if not isinstance(hoja.get(c), str) or not hoja[c].strip()]
                fecha = date.fromisoformat(hoja.get("fecha_nacimiento", ""))
            except (ValueError, AttributeError, TypeError):
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
        except Exception as e:
            # Un error inesperado también rechaza el envío, para que no bloquee a los siguientes.
            if not isinstance(e, ReglaNegocioError):
                logger.exception("Error inesperado al importar %s", pdf.name)
            motivo = str(e) if isinstance(e, ReglaNegocioError) else f"Error inesperado al cargar ({type(e).__name__})."
            enviados = [pdf] + ([datos_json] if datos_json.exists() or datos_json.is_symlink() else [])
            archivado = _archivar(carpeta / "rechazados", *enviados)[0]
            try:
                (carpeta / "rechazados" / f"{archivado.stem}.motivo.txt").write_text(motivo + "\n", encoding="utf-8")
            except OSError:
                logger.exception("No se pudo escribir el motivo de rechazo de %s", pdf.name)
            registrar(usuario, "Importación rechazada", detalle=f"{pdf.name}: {motivo}")
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
    return enviar_aviso_automatico(resultado)


# ---------- Entrega ----------

def tiene_acceso_digital(paciente):
    return Usuario.objects.filter(paciente=paciente, is_active=True).exists()


def _canal_disponible(paciente, excluir=None):
    disponibles = [(c, d) for c, d in [(Notificacion.Canal.CORREO, paciente.correo),
                                       (Notificacion.Canal.SMS, paciente.telefono)] if d]
    for canal, destino in disponibles:
        if canal != excluir:
            return canal, destino
    return disponibles[0] if disponibles else (None, None)


def _olvidar_aviso_en_cache(resultado):
    for atributo in ("ultimo_aviso", "avance", "le_toca"):
        resultado.__dict__.pop(atributo, None)


def _crear_aviso(resultado, canal, destino, intento):
    _olvidar_aviso_en_cache(resultado)
    return Notificacion.objects.create(
        resultado=resultado, canal=canal, destino=destino, intento=intento,
        mensaje=MENSAJE_AVISO.format(nombre=resultado.paciente.nombre.split()[0]),
    )


def _marcar_entrega_asistida(resultado, motivo):
    resultado.requiere_entrega_asistida = True
    resultado.save(update_fields=["requiere_entrega_asistida", "actualizado"])
    registrar(None, "Requiere entrega asistida", resultado, detalle=motivo)


def enviar_aviso_automatico(resultado):
    paciente = resultado.paciente
    if not tiene_acceso_digital(paciente):
        _marcar_entrega_asistida(resultado, "La paciente no tiene acceso al portal.")
        return None
    canal, destino = _canal_disponible(paciente)
    if canal is None:
        _marcar_entrega_asistida(resultado, "La paciente no tiene correo ni teléfono registrados.")
        return None
    aviso = _crear_aviso(resultado, canal, destino, intento=1)
    _transicionar(resultado, None, Estado.NOTIFICADO,
                  f"Aviso automático por {Notificacion.Canal(canal).label.lower()}",
                  f"Destino: {enmascarar(destino)}", sistema=True)
    return aviso


def _aviso_pendiente(resultado, usuario, estado_esperado, error):
    if usuario.rol != Rol.EIRA:
        raise ReglaNegocioError("Tu rol no puede realizar esta acción.")
    aviso = resultado.ultimo_aviso
    if resultado.estado != Estado.NOTIFICADO or aviso is None or aviso.estado != estado_esperado:
        raise ReglaNegocioError(error)
    return aviso


@transaction.atomic
def simular_fallo_aviso(resultado, usuario):
    aviso = _aviso_pendiente(resultado, usuario, Notificacion.Estado.ENVIADA, "No hay un aviso enviado que pueda fallar.")
    aviso.estado = Notificacion.Estado.FALLIDA
    aviso.save(update_fields=["estado"])
    _olvidar_aviso_en_cache(resultado)
    registrar(usuario, "Fallo de entrega del aviso (simulado)", resultado,
              detalle=f"Intento {aviso.intento} por {aviso.get_canal_display().lower()}.")
    fallos = resultado.notificaciones.filter(estado=Notificacion.Estado.FALLIDA).count()
    if fallos >= MAX_FALLOS_AVISO:
        _marcar_entrega_asistida(resultado, f"{fallos} intentos de aviso fallidos.")


@transaction.atomic
def reintentar_aviso(resultado, usuario):
    aviso = _aviso_pendiente(resultado, usuario, Notificacion.Estado.FALLIDA, "Solo se puede reintentar un aviso que falló.")
    if resultado.requiere_entrega_asistida:
        raise ReglaNegocioError("Se alcanzó el límite de intentos: registra una entrega asistida.")
    canal, destino = _canal_disponible(resultado.paciente, excluir=aviso.canal)
    nuevo = _crear_aviso(resultado, canal, destino, intento=aviso.intento + 1)
    registrar(usuario, f"Reintento de aviso por {nuevo.get_canal_display().lower()}", resultado,
              detalle=f"Intento {nuevo.intento}. Destino: {enmascarar(destino)}")
    return nuevo


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
