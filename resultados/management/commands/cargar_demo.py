import json
import shutil
from datetime import date
from pathlib import Path

from django.conf import settings
from django.core.files import File
from django.core.management.base import BaseCommand

from resultados import servicios
from resultados.models import Paciente, Resultado, Usuario

DATOS = Path(settings.BASE_DIR) / "datos_demo"


class Command(BaseCommand):
    help = "Crea pacientes y usuarios ficticios. Con --con-resultados también carga los 5 PDFs de ejemplo."

    def add_arguments(self, parser):
        parser.add_argument("--con-resultados", action="store_true", help="Carga los PDFs sintéticos como 'Cargado'.")
        parser.add_argument("--a-bandeja", action="store_true",
                            help="Copia los PDFs sintéticos (con su .json) a la bandeja de entrada, como lo haría el laboratorio.")

    def handle(self, *args, con_resultados=False, a_bandeja=False, **opciones):
        pacientes = {}
        for p in json.loads((DATOS / "pacientes.json").read_text(encoding="utf-8")):
            pacientes[p["id"]], _ = Paciente.objects.update_or_create(
                folio_expediente=p["folio_expediente"],
                defaults={
                    "nombre": p["nombre"], "fecha_nacimiento": date.fromisoformat(p["fecha_nacimiento"]),
                    "correo": p["correo"], "telefono": p["telefono"], "preferencia_entrega": p["preferencia_entrega"],
                },
            )
        for u in json.loads((DATOS / "usuarios.json").read_text(encoding="utf-8")):
            usuario, _ = Usuario.objects.update_or_create(
                username=u["correo"],
                defaults={
                    "email": u["correo"], "first_name": u["nombre"], "rol": u["rol"],
                    "paciente": pacientes.get(u["paciente_id"]),
                },
            )
            usuario.set_password(u["password_demo"])
            usuario.save()
        self.stdout.write(self.style.SUCCESS(f"{len(pacientes)} pacientes y {Usuario.objects.count()} usuarios listos."))

        if con_resultados:
            laboratorio = Usuario.objects.get(username="laboratorio@lab.test")
            for r in json.loads((DATOS / "resultados.json").read_text(encoding="utf-8")):
                if Resultado.objects.filter(folio_laboratorio=r["hoja"]["folio_laboratorio"]).exists():
                    continue
                with open(DATOS / "pdfs" / r["archivo"], "rb") as f:
                    servicios.cargar_resultado(
                        laboratorio, File(f, name=r["archivo"]),
                        hoja_nombre=r["hoja"]["nombre"],
                        hoja_fecha_nacimiento=date.fromisoformat(r["hoja"]["fecha_nacimiento"]),
                        hoja_folio_expediente=r["hoja"]["folio_expediente"],
                        folio_laboratorio=r["hoja"]["folio_laboratorio"],
                    )
            self.stdout.write(self.style.SUCCESS("PDFs de ejemplo cargados."))

        if a_bandeja:
            carpeta = Path(settings.CARPETA_ENTRADA)
            carpeta.mkdir(parents=True, exist_ok=True)
            for r in json.loads((DATOS / "resultados.json").read_text(encoding="utf-8")):
                shutil.copy(DATOS / "pdfs" / r["archivo"], carpeta / r["archivo"])
                (carpeta / r["archivo"]).with_suffix(".json").write_text(
                    json.dumps(r["hoja"], ensure_ascii=False, indent=2), encoding="utf-8")
            self.stdout.write(self.style.SUCCESS(f"PDFs de ejemplo copiados a {carpeta}."))
