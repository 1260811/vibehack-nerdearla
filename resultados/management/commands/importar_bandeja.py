import time

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from resultados import servicios
from resultados.models import Usuario


class Command(BaseCommand):
    help = "Carga los PDFs que el laboratorio dejó en la bandeja de entrada (cada uno con su .json)."

    def add_arguments(self, parser):
        parser.add_argument("--carpeta", help="Por defecto, CARPETA_ENTRADA (variable EIRA_CARPETA_ENTRADA).")
        parser.add_argument("--usuario", default=settings.USUARIO_BANDEJA, help="Usuario de laboratorio que firma la carga.")
        parser.add_argument("--vigilar", type=int, metavar="SEGUNDOS", help="Revisa la carpeta cada N segundos.")

    def handle(self, *args, carpeta=None, usuario=None, vigilar=None, **opciones):
        try:
            usuario = Usuario.objects.get(username=usuario)
        except Usuario.DoesNotExist:
            raise CommandError(f"No existe el usuario {usuario}.")
        carpeta = carpeta or settings.CARPETA_ENTRADA
        while True:
            cargados, rechazados = servicios.importar_bandeja(usuario, carpeta)
            for r in cargados:
                self.stdout.write(self.style.SUCCESS(f"Cargado {r.folio_laboratorio}"))
            for nombre, motivo in rechazados:
                self.stdout.write(self.style.ERROR(f"Rechazado {nombre}: {motivo}"))
            if not vigilar:
                break
            time.sleep(vigilar)
        self.stdout.write(f"{len(cargados)} cargado(s), {len(rechazados)} rechazado(s) en {carpeta}.")
