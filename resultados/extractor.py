"""Lectura automática (OCR local) de los datos impresos en la hoja del laboratorio.

Solo propone valores: la persona que carga los confirma y EIRA los vuelve a comparar con el expediente.
"""
import re
import shutil
import subprocess
import unicodedata
from datetime import date
from difflib import SequenceMatcher

import pymupdf

CONFIANZA_MINIMA = 85
DPI_OCR = 300
PIXELES_MAXIMOS = 12_000_000  # una hoja carta a 300 DPI son ~8.4 millones
ETIQUETAS = {
    "hoja_nombre": "paciente",
    "hoja_fecha_nacimiento": "fecha de nacimiento",
    "hoja_folio_expediente": "folio de expediente",
    "folio_laboratorio": "folio de laboratorio",
}
FOLIO = re.compile(r"^[A-Z]{2,6}-\d{3,8}$")


class ExtraccionError(Exception):
    pass


def ocr_disponible():
    return shutil.which("tesseract") is not None


def _normalizar(texto):
    sin_acentos = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z ]", "", sin_acentos.lower()).strip()


def _lineas_ocr(png):
    salida = subprocess.run(["tesseract", "stdin", "stdout", "-l", "spa", "--psm", "6", "tsv"],
                            input=png, capture_output=True, timeout=60, check=True).stdout.decode()
    lineas = {}
    for fila in salida.splitlines()[1:]:
        c = fila.split("\t")
        if len(c) == 12 and c[0] == "5" and c[11].strip():
            lineas.setdefault((c[2], c[3], c[4]), []).append((c[11], float(c[10])))
    return list(lineas.values())


def _lineas_texto(texto):
    return [[(p, 100.0) for p in linea.split()] for linea in texto.splitlines() if linea.strip()]


def _separar(palabras):
    """Devuelve (campo, palabras del valor) si la línea empieza con una etiqueta conocida."""
    mejor = (0.0, None, 0)
    for n in range(1, min(4, len(palabras)) + 1):
        etiqueta = _normalizar(" ".join(p for p, _ in palabras[:n]))
        for campo, esperada in ETIQUETAS.items():
            parecido = SequenceMatcher(None, etiqueta, esperada).ratio()
            if parecido > mejor[0]:
                mejor = (parecido, campo, n)
    parecido, campo, n = mejor
    return (campo, palabras[n:]) if parecido >= 0.8 else (None, [])


def _validar(campo, valor):
    if campo == "hoja_nombre":
        return valor if re.fullmatch(r"[A-Za-zÁÉÍÓÚÜÑáéíóúüñ' .-]{5,150}", valor) else ""
    if campo == "hoja_fecha_nacimiento":
        m = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", valor) or re.fullmatch(r"(\d{2})/(\d{2})/(\d{4})", valor)
        if not m:
            return ""
        a, me, d = (m.group(1), m.group(2), m.group(3)) if "-" in valor else (m.group(3), m.group(2), m.group(1))
        try:
            f = date(int(a), int(me), int(d))
        except ValueError:
            return ""
        return f.isoformat() if 1900 <= f.year <= date.today().year else ""
    valor = valor.upper().replace(" ", "-")
    return valor if FOLIO.fullmatch(valor) else ""


def interpretar(lineas):
    campos = {c: {"valor": "", "confianza": 0, "revisar": True} for c in ETIQUETAS}
    for palabras in lineas:
        campo, resto = _separar(palabras)
        if not campo or campos[campo]["valor"] or not resto:
            continue
        valor = _validar(campo, " ".join(p for p, _ in resto).strip(" :.;"))
        if valor:
            confianza = round(sum(c for _, c in resto) / len(resto))
            campos[campo] = {"valor": valor, "confianza": confianza, "revisar": confianza < CONFIANZA_MINIMA}
    return campos


def extraer_datos(archivo):
    """Lee la primera página del PDF; usa su texto si lo tiene y, si es un escaneo, OCR local."""
    try:
        with pymupdf.open(stream=archivo.read(), filetype="pdf") as doc:
            pagina = doc[0]
            campos = interpretar(_lineas_texto(pagina.get_text()))
            if any(c["valor"] for c in campos.values()):
                return campos
            if not ocr_disponible():
                raise ExtraccionError("La lectura automática no está instalada en este servidor.")
            puntos = pagina.rect.width * pagina.rect.height
            dpi = min(DPI_OCR, int(72 * (PIXELES_MAXIMOS / puntos) ** 0.5)) if puntos > 0 else 0
            if dpi < 150:
                raise ExtraccionError("La página es demasiado grande para leerla automáticamente.")
            png = pagina.get_pixmap(dpi=dpi, colorspace=pymupdf.csGRAY).tobytes("png")
    except (RuntimeError, ValueError, IndexError) as e:
        raise ExtraccionError("No se pudo abrir el PDF.") from e
    finally:
        archivo.seek(0)
    try:
        return interpretar(_lineas_ocr(png))
    except (subprocess.SubprocessError, OSError) as e:
        raise ExtraccionError("No se pudo leer el PDF automáticamente.") from e
