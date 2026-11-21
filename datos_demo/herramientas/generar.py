"""Genera datos sintéticos (pacientes, usuarios, resultados PDF con aspecto de escaneo)."""
import hashlib, io, json, random
from pathlib import Path
import fitz
from PIL import Image, ImageFilter, ImageEnhance
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

BASE = Path(__file__).resolve().parent.parent
FONTS = "/usr/share/fonts/truetype/dejavu/"
pdfmetrics.registerFont(TTFont("Sans", FONTS + "DejaVuSans.ttf"))
pdfmetrics.registerFont(TTFont("SansB", FONTS + "DejaVuSans-Bold.ttf"))
random.seed(42)

PASSWORD_DEMO = "Demo2026!"

pacientes = [
    {"id": "P1", "nombre": "María López Hernández", "fecha_nacimiento": "1988-03-14", "folio_expediente": "EIRA-0001",
     "correo": "maria.lopez.88@ejemplo.test", "telefono": "+52 55 5550 0101", "preferencia_entrega": "digital"},
    {"id": "P2", "nombre": "María López Hernández", "fecha_nacimiento": "1992-07-02", "folio_expediente": "EIRA-0002",
     "correo": "maria.lopez.92@ejemplo.test", "telefono": "+52 55 5550 0102", "preferencia_entrega": "digital"},
    {"id": "P3", "nombre": "Rosa Elena Martínez Cruz", "fecha_nacimiento": "1975-11-23", "folio_expediente": "EIRA-0003",
     "correo": None, "telefono": "+52 55 5550 0103", "preferencia_entrega": "asistida"},
    {"id": "P4", "nombre": "Ana Sofía Ramírez Torres", "fecha_nacimiento": "1999-01-30", "folio_expediente": "EIRA-0004",
     "correo": "ana.ramirez@ejemplo.test", "telefono": "+52 55 5550 0104", "preferencia_entrega": "digital"},
]

usuarios = [
    {"correo": "laboratorio@lab.test", "nombre": "Laboratorio Clínico Ficticio", "rol": "laboratorio", "paciente_id": None},
    {"correo": "admin@eira.test", "nombre": "Lucía Admin (EIRA)", "rol": "eira", "paciente_id": None},
    {"correo": "medico@eira.test", "nombre": "Dra. Carmen Médica Ficticia", "rol": "medico", "paciente_id": None},
    {"correo": "maria.lopez.88@ejemplo.test", "nombre": "María López Hernández", "rol": "paciente", "paciente_id": "P1"},
    {"correo": "maria.lopez.92@ejemplo.test", "nombre": "María López Hernández", "rol": "paciente", "paciente_id": "P2"},
    {"correo": "ana.ramirez@ejemplo.test", "nombre": "Ana Sofía Ramírez Torres", "rol": "paciente", "paciente_id": "P4"},
]
for u in usuarios:
    u["password_demo"] = PASSWORD_DEMO

NILM = "Negativo para lesión intraepitelial o malignidad (NILM)"
LSIL = "Lesión intraepitelial escamosa de bajo grado (LSIL)"
resultados = [
    {"id": "R1", "archivo": "R1_LAB-24001.pdf", "escenario": "Flujo feliz: coincide con P1, resultado normal",
     "hoja": {"nombre": "María López Hernández", "fecha_nacimiento": "1988-03-14", "folio_expediente": "EIRA-0001", "folio_laboratorio": "LAB-24001"},
     "interpretacion": NILM, "paciente_esperada": "P1", "requiere_contacto_sugerido": False, "calidad": "buena"},
    {"id": "R2", "archivo": "R2_LAB-24002.pdf", "escenario": "Homónima: mismo nombre que P1, solo coincide con P2 por fecha y folio; resultado anormal",
     "hoja": {"nombre": "María López Hernández", "fecha_nacimiento": "1992-07-02", "folio_expediente": "EIRA-0002", "folio_laboratorio": "LAB-24002"},
     "interpretacion": LSIL, "paciente_esperada": "P2", "requiere_contacto_sugerido": True, "calidad": "buena"},
    {"id": "R3", "archivo": "R3_LAB-24003.pdf", "escenario": "Entrega asistida: P3 no tiene correo ni usuario",
     "hoja": {"nombre": "Rosa Elena Martínez Cruz", "fecha_nacimiento": "1975-11-23", "folio_expediente": "EIRA-0003", "folio_laboratorio": "LAB-24003"},
     "interpretacion": NILM, "paciente_esperada": "P3", "requiere_contacto_sugerido": False, "calidad": "buena"},
    {"id": "R4", "archivo": "R4_LAB-24004.pdf", "escenario": "Datos no coinciden: nombre de P4 pero fecha y folio distintos; la asociación debe bloquearse",
     "hoja": {"nombre": "Ana Sofía Ramírez Torres", "fecha_nacimiento": "1999-03-01", "folio_expediente": "EIRA-0044", "folio_laboratorio": "LAB-24004"},
     "interpretacion": NILM, "paciente_esperada": None, "requiere_contacto_sugerido": False, "calidad": "buena"},
    {"id": "R5", "archivo": "R5_LAB-24005.pdf", "escenario": "Escaneo ilegible: coincide con P4 pero EIRA debe devolverlo en revisión",
     "hoja": {"nombre": "Ana Sofía Ramírez Torres", "fecha_nacimiento": "1999-01-30", "folio_expediente": "EIRA-0004", "folio_laboratorio": "LAB-24005"},
     "interpretacion": NILM, "paciente_esperada": "P4", "requiere_contacto_sugerido": False, "calidad": "ilegible"},
]


def pdf_limpio(r):
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=letter)
    w, h = letter
    c.saveState()
    c.setFillGray(0.85)
    c.setFont("SansB", 40)
    c.translate(w / 2, h / 2)
    c.rotate(35)
    c.drawCentredString(0, 0, "DOCUMENTO SINTÉTICO")
    c.setFont("SansB", 20)
    c.drawCentredString(0, -36, "Solo para demostración · No válido")
    c.restoreState()

    c.setFont("SansB", 15)
    c.drawString(2 * cm, h - 2.2 * cm, "Laboratorio Clínico Ficticio Ejemplo")
    c.setFont("Sans", 8.5)
    c.drawString(2 * cm, h - 2.75 * cm, "Av. Imaginaria 123, Ciudad Ejemplo · Tel. 55 5550 0000 · DATOS FICTICIOS")
    c.line(2 * cm, h - 3.1 * cm, w - 2 * cm, h - 3.1 * cm)
    c.setFont("SansB", 12.5)
    c.drawCentredString(w / 2, h - 4 * cm, "REPORTE DE CITOLOGÍA CERVICOVAGINAL (PAPANICOLAOU)")

    hj = r["hoja"]
    filas = [
        ("Paciente:", hj["nombre"]), ("Fecha de nacimiento:", hj["fecha_nacimiento"]),
        ("Folio de expediente:", hj["folio_expediente"]), ("Folio de laboratorio:", hj["folio_laboratorio"]),
        ("Institución solicitante:", "EIRA (ficticia)"), ("Fecha de toma:", "2026-11-09"),
        ("Fecha de emisión:", "2026-11-18"), ("Tipo de muestra:", "Citología convencional"),
    ]
    y = h - 5.2 * cm
    for k, v in filas:
        c.setFont("SansB", 10); c.drawString(2 * cm, y, k)
        c.setFont("Sans", 10); c.drawString(7 * cm, y, v)
        y -= 0.62 * cm

    y -= 0.4 * cm
    secciones = [
        ("Calidad de la muestra", "Satisfactoria para evaluación."),
        ("Categoría general", "Ver interpretación."),
        ("Interpretación (Sistema Bethesda)", r["interpretacion"]),
        ("Comentarios", "Resultado generado artificialmente para pruebas de software."),
    ]
    for t, v in secciones:
        c.setFont("SansB", 10.5); c.drawString(2 * cm, y, t); y -= 0.55 * cm
        c.setFont("Sans", 10); c.drawString(2.4 * cm, y, v); y -= 0.85 * cm

    c.line(w - 8.5 * cm, 4.2 * cm, w - 2 * cm, 4.2 * cm)
    c.setFont("Sans", 9)
    c.drawCentredString(w - 5.25 * cm, 3.7 * cm, "Q.F.B. Nombre Ficticio")
    c.drawCentredString(w - 5.25 * cm, 3.3 * cm, "Citotecnóloga responsable (ficticia)")
    c.setFont("Sans", 7.5)
    c.drawCentredString(w / 2, 1.5 * cm, "Este documento es sintético y no contiene datos reales de ninguna persona.")
    c.showPage(); c.save()
    return buf.getvalue()


def escanear(pdf_bytes, calidad):
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    pix = doc[0].get_pixmap(dpi=130)
    img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples).convert("L")
    angulo = random.uniform(-1.4, 1.4)
    img = img.rotate(angulo, resample=Image.BICUBIC, expand=False, fillcolor=245)
    ruido = Image.effect_noise(img.size, 18 if calidad == "buena" else 45)
    img = Image.blend(img, ruido, 0.06 if calidad == "buena" else 0.18)
    if calidad == "ilegible":
        img = img.filter(ImageFilter.GaussianBlur(2.0))
        img = ImageEnhance.Contrast(img).enhance(0.6)
        img = ImageEnhance.Brightness(img).enhance(1.12)
    tinte = Image.merge("RGB", (img, img, img.point(lambda p: int(p * 0.93))))
    out = io.BytesIO()
    jpg = io.BytesIO(); tinte.save(jpg, "JPEG", quality=55); jpg.seek(0)
    Image.open(jpg).save(out, "PDF", resolution=130)
    return out.getvalue()


for r in resultados:
    data = escanear(pdf_limpio(r), r["calidad"])
    (BASE / "pdfs" / r["archivo"]).write_bytes(data)
    r["sha256"] = hashlib.sha256(data).hexdigest()

for nombre, obj in [("pacientes.json", pacientes), ("usuarios.json", usuarios), ("resultados.json", resultados)]:
    (BASE / nombre).write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print("ok", len(resultados), "PDFs")
