import json
import os
import shutil
import tempfile
from pathlib import Path
from unittest import mock

from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse

from . import servicios
from .models import Estado, EventoBitacora, Notificacion, Paciente, Resultado, Usuario

MEDIA_TEMPORAL = tempfile.mkdtemp()


@override_settings(MEDIA_ROOT=MEDIA_TEMPORAL)
class FlujoTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("cargar_demo", "--con-resultados", verbosity=0)

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(MEDIA_TEMPORAL, ignore_errors=True)

    def setUp(self):
        self.lab = Usuario.objects.get(username="laboratorio@lab.test")
        self.eira = Usuario.objects.get(username="admin@eira.test")
        self.medico = Usuario.objects.get(username="medico@eira.test")
        self.p1 = Paciente.objects.get(folio_expediente="EIRA-0001")
        self.p2 = Paciente.objects.get(folio_expediente="EIRA-0002")
        self.p3 = Paciente.objects.get(folio_expediente="EIRA-0003")
        self.p4 = Paciente.objects.get(folio_expediente="EIRA-0004")

    def resultado(self, folio):
        return Resultado.objects.get(folio_laboratorio=folio)

    def llevar_a_autorizado(self, r, paciente):
        servicios.asociar(r, paciente, self.eira)
        servicios.aprobar_revision(r, self.eira)
        servicios.autorizar(r, self.medico)

    def test_flujo_feliz_hasta_consulta(self):
        r = self.resultado("LAB-24001")
        self.llevar_a_autorizado(r, self.p1)
        servicios.notificar(r, self.eira, Notificacion.Canal.CORREO)
        self.assertEqual(r.estado, Estado.NOTIFICADO)
        aviso = Notificacion.objects.get(resultado=r)
        self.assertNotIn("NILM", aviso.mensaje)

        self.client.login(username="maria.lopez.88@ejemplo.test", password="Demo2026!")
        respuesta = self.client.get(reverse("documento", args=[r.pk]))
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta["Content-Type"], "application/pdf")
        r.refresh_from_db()
        self.assertEqual(r.estado, Estado.CONSULTADO)
        acciones = list(r.eventos.order_by("fecha", "id").values_list("accion", flat=True))
        self.assertEqual(acciones[0], "Carga de PDF")
        self.assertEqual(acciones[-1], "Consulta por la paciente")

    def test_consulta_simultanea_no_falla(self):
        r = self.resultado("LAB-24001")
        self.llevar_a_autorizado(r, self.p1)
        servicios.notificar(r, self.eira, Notificacion.Canal.CORREO)
        paciente = r.paciente.usuario
        copia_vieja = Resultado.objects.get(pk=r.pk)
        servicios.registrar_acceso(paciente, r)
        servicios.registrar_acceso(paciente, copia_vieja, descarga=True)
        self.assertEqual(copia_vieja.estado, Estado.CONSULTADO)
        self.assertTrue(r.eventos.filter(accion="Descarga del documento").exists())

    def test_homonima_solo_se_asocia_con_datos_completos(self):
        r = self.resultado("LAB-24002")
        with self.assertRaises(servicios.ReglaNegocioError):
            servicios.asociar(r, self.p1, self.eira)
        servicios.asociar(r, self.p2, self.eira)
        self.assertEqual(r.paciente, self.p2)
        self.assertTrue(EventoBitacora.objects.filter(resultado=r, accion="Asociación bloqueada").exists())

    def test_datos_que_no_coinciden_bloquean_asociacion(self):
        r = self.resultado("LAB-24004")
        candidatos = servicios.candidatos(r)
        self.assertFalse(any(c["coincide_todo"] for c in candidatos))
        with self.assertRaises(servicios.ReglaNegocioError):
            servicios.asociar(r, self.p4, self.eira)
        r.refresh_from_db()
        self.assertEqual(r.estado, Estado.CARGADO)

    def test_no_se_pueden_saltar_estados_ni_roles(self):
        r = self.resultado("LAB-24001")
        with self.assertRaises(servicios.ReglaNegocioError):
            servicios.autorizar(r, self.medico)
        servicios.asociar(r, self.p1, self.eira)
        with self.assertRaises(servicios.ReglaNegocioError):
            servicios.autorizar(r, self.eira)
        with self.assertRaises(servicios.ReglaNegocioError):
            servicios.aprobar_revision(r, self.lab)

    def test_transicion_con_datos_desactualizados_no_sobrescribe(self):
        r = self.resultado("LAB-24005")
        servicios.asociar(r, self.p4, self.eira)
        copia_vieja = Resultado.objects.get(pk=r.pk)
        servicios.devolver(r, self.eira, "Escaneo ilegible")
        with self.assertRaises(servicios.ReglaNegocioError):
            servicios.aprobar_revision(copia_vieja, self.eira)
        r.refresh_from_db()
        self.assertEqual(r.estado, Estado.DEVUELTO)
        self.assertEqual(r.motivo_devolucion, "Escaneo ilegible")

    def test_devolver_exige_motivo(self):
        r = self.resultado("LAB-24005")
        servicios.asociar(r, self.p4, self.eira)
        with self.assertRaises(servicios.ReglaNegocioError):
            servicios.devolver(r, self.eira, "  ")
        servicios.devolver(r, self.eira, "Escaneo ilegible")
        self.assertEqual(r.estado, Estado.DEVUELTO)

    def test_paciente_sin_acceso_digital_requiere_entrega_asistida(self):
        r = self.resultado("LAB-24003")
        self.llevar_a_autorizado(r, self.p3)
        with self.assertRaises(servicios.ReglaNegocioError):
            servicios.notificar(r, self.eira, Notificacion.Canal.SMS)
        servicios.registrar_entrega_asistida(r, self.eira, "La paciente en recepción", "INE")
        self.assertEqual(r.estado, Estado.ENTREGADO_ASISTIDO)

    def test_paciente_no_ve_documento_ajeno_ni_no_autorizado(self):
        r1, r2 = self.resultado("LAB-24001"), self.resultado("LAB-24002")
        servicios.asociar(r1, self.p1, self.eira)
        self.llevar_a_autorizado(r2, self.p2)
        self.client.login(username="maria.lopez.88@ejemplo.test", password="Demo2026!")
        self.assertEqual(self.client.get(reverse("documento", args=[r2.pk])).status_code, 404)
        self.assertEqual(self.client.get(reverse("documento", args=[r1.pk])).status_code, 404)
        self.assertEqual(self.client.get(reverse("panel")).status_code, 403)

    def test_documento_exige_sesion(self):
        r = self.resultado("LAB-24001")
        respuesta = self.client.get(reverse("documento", args=[r.pk]))
        self.assertEqual(respuesta.status_code, 302)
        self.assertIn(reverse("login"), respuesta["Location"])

    def test_carga_rechaza_archivos_que_no_son_pdf(self):
        falso = SimpleUploadedFile("x.pdf", b"no soy un pdf", content_type="application/pdf")
        with self.assertRaises(servicios.ReglaNegocioError):
            servicios.cargar_resultado(self.lab, falso, "X", "2000-01-01", "EIRA-9", "LAB-9")

    def test_bitacora_es_de_solo_insercion(self):
        evento = EventoBitacora.objects.first()
        evento.detalle = "alterado"
        with self.assertRaises(ValidationError):
            evento.save()
        with self.assertRaises(ValidationError):
            evento.delete()

    def test_archivo_alterado_no_se_entrega(self):
        r = self.resultado("LAB-24001")
        with open(r.archivo.path, "rb") as f:
            original = f.read()
        try:
            with open(r.archivo.path, "ab") as f:
                f.write(b"alterado")
            self.client.login(username="admin@eira.test", password="Demo2026!")
            self.assertEqual(self.client.get(reverse("documento", args=[r.pk])).status_code, 409)
        finally:
            with open(r.archivo.path, "wb") as f:
                f.write(original)

    def test_pantallas_principales_por_rol(self):
        r = self.resultado("LAB-24002")
        for correo, url in [
            ("laboratorio@lab.test", reverse("laboratorio")),
            ("admin@eira.test", reverse("panel")),
            ("admin@eira.test", reverse("detalle", args=[r.pk])),
            ("admin@eira.test", reverse("avisos")),
            ("admin@eira.test", reverse("bitacora")),
            ("medico@eira.test", reverse("medico")),
            ("maria.lopez.92@ejemplo.test", reverse("mis_resultados")),
        ]:
            self.client.login(username=correo, password="Demo2026!")
            self.assertEqual(self.client.get(url).status_code, 200, url)


@override_settings(MEDIA_ROOT=MEDIA_TEMPORAL)
class BandejaYPanelTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("cargar_demo", verbosity=0)

    def setUp(self):
        self.lab = Usuario.objects.get(username="laboratorio@lab.test")
        self.eira = Usuario.objects.get(username="admin@eira.test")
        self.carpeta = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.carpeta, ignore_errors=True)
        ajustes = override_settings(CARPETA_ENTRADA=self.carpeta, SEGUNDOS_ESPERA_BANDEJA=0)
        ajustes.enable()
        self.addCleanup(ajustes.disable)

    def test_importa_pdfs_de_la_bandeja_y_los_mueve(self):
        call_command("cargar_demo", "--a-bandeja", verbosity=0)
        cargados, rechazados = servicios.importar_bandeja(self.lab)
        self.assertEqual((len(cargados), rechazados), (5, []))
        self.assertEqual(servicios.pendientes_en_bandeja(), [])
        self.assertEqual(len(list((self.carpeta / "procesados").glob("*.pdf"))), 5)
        r = Resultado.objects.get(folio_laboratorio="LAB-24001")
        self.assertEqual((r.estado, r.cargado_por), (Estado.CARGADO, self.lab))
        self.assertIn("Bandeja de entrada", r.eventos.get(accion="Carga de PDF").detalle)

    def test_bandeja_rechaza_sin_datos_duplicados_y_no_pdf(self):
        call_command("cargar_demo", "--a-bandeja", verbosity=0)
        (self.carpeta / "R2_LAB-24002.json").unlink()
        (self.carpeta / "falso.pdf").write_bytes(b"no soy un pdf")
        (self.carpeta / "falso.json").write_text(json.dumps({
            "nombre": "X", "fecha_nacimiento": "2000-01-01", "folio_expediente": "EIRA-9", "folio_laboratorio": "LAB-9",
        }))
        servicios.importar_bandeja(self.lab)
        call_command("cargar_demo", "--a-bandeja", verbosity=0)
        cargados, rechazados = servicios.importar_bandeja(self.lab)
        motivos = dict(rechazados)
        self.assertEqual([r.folio_laboratorio for r in cargados], ["LAB-24002"])
        self.assertIn("ya fue cargado", motivos["R1_LAB-24001.pdf"])
        self.assertTrue((self.carpeta / "rechazados" / "falso.motivo.txt").exists())
        self.assertTrue(EventoBitacora.objects.filter(accion="Importación rechazada", detalle__contains="Falta").exists())
        self.assertFalse(Resultado.objects.filter(folio_laboratorio="LAB-9").exists())

    def test_boton_importar_bandeja(self):
        call_command("cargar_demo", "--a-bandeja", verbosity=0)
        self.client.login(username="laboratorio@lab.test", password="Demo2026!")
        respuesta = self.client.post(reverse("importar_bandeja"), follow=True)
        self.assertContains(respuesta, "5 documento(s) importado(s)")
        self.client.login(username="medico@eira.test", password="Demo2026!")
        self.assertEqual(self.client.post(reverse("importar_bandeja")).status_code, 403)

    def test_bandeja_rechaza_enlaces_simbolicos_y_json_enorme(self):
        call_command("cargar_demo", "--a-bandeja", verbosity=0)
        externo = self.carpeta.parent / f"{self.carpeta.name}-externo.pdf"
        shutil.move(self.carpeta / "R1_LAB-24001.pdf", externo)
        self.addCleanup(externo.unlink)
        os.symlink(externo, self.carpeta / "R1_LAB-24001.pdf")
        (self.carpeta / "R2_LAB-24002.json").write_text(" " * (servicios.TAMANO_MAXIMO_JSON + 1))
        cargados, rechazados = servicios.importar_bandeja(self.lab)
        motivos = dict(rechazados)
        self.assertEqual(len(cargados), 3)
        self.assertIn("enlaces simbólicos", motivos["R1_LAB-24001.pdf"])
        self.assertIn("demasiado grande", motivos["R2_LAB-24002.pdf"])

    def test_bandeja_espera_archivos_que_se_estan_copiando(self):
        call_command("cargar_demo", "--a-bandeja", verbosity=0)
        with override_settings(SEGUNDOS_ESPERA_BANDEJA=60):
            self.assertEqual(servicios.importar_bandeja(self.lab), ([], []))
        self.assertEqual(len(servicios.pendientes_en_bandeja()), 5)

    def test_importaciones_simultaneas_no_toman_el_mismo_pdf(self):
        call_command("cargar_demo", "--a-bandeja", verbosity=0)
        pdf = self.carpeta / "R1_LAB-24001.pdf"
        otra = Path(tempfile.mkdtemp(dir=self.carpeta))
        self.assertEqual(servicios._reclamar(pdf, otra), otra / pdf.name)
        cargados, _ = servicios.importar_bandeja(self.lab)
        self.assertNotIn("LAB-24001", [r.folio_laboratorio for r in cargados])
        self.assertEqual(sorted(p.name for p in self.carpeta.glob(".importando-*")), [])

    def test_rechazos_con_el_mismo_nombre_no_se_pisan(self):
        for _ in range(2):
            (self.carpeta / "falso.pdf").write_bytes(b"no soy un pdf")
            servicios.importar_bandeja(self.lab)
        rechazados = self.carpeta / "rechazados"
        self.assertEqual(len(list(rechazados.glob("falso*.pdf"))), 2)
        self.assertEqual(len(list(rechazados.glob("falso*.motivo.txt"))), 2)

    def test_bandeja_rechaza_campos_que_no_son_texto(self):
        call_command("cargar_demo", "--a-bandeja", verbosity=0)
        datos = self.carpeta / "R1_LAB-24001.json"
        hoja = json.loads(datos.read_text())
        datos.write_text(json.dumps({**hoja, "fecha_nacimiento": None}))
        (self.carpeta / "R2_LAB-24002.json").write_text(json.dumps({**hoja, "nombre": 7, "folio_laboratorio": "LAB-7"}))
        cargados, rechazados = servicios.importar_bandeja(self.lab)
        self.assertEqual(len(cargados), 3)
        self.assertEqual(sorted(dict(rechazados)), ["R1_LAB-24001.pdf", "R2_LAB-24002.pdf"])
        self.assertEqual(list(self.carpeta.glob(".importando-*")), [])

    def test_error_inesperado_rechaza_el_envio_y_sigue(self):
        call_command("cargar_demo", "--a-bandeja", verbosity=0)
        original = servicios.cargar_resultado

        def falla_con_r1(usuario, archivo, **datos):
            if datos["folio_laboratorio"] == "LAB-24001":
                raise OSError("disco lleno")
            return original(usuario, archivo, **datos)

        with mock.patch.object(servicios, "cargar_resultado", falla_con_r1), self.assertLogs("resultados.servicios"):
            cargados, rechazados = servicios.importar_bandeja(self.lab)
        self.assertEqual(len(cargados), 4)
        self.assertIn("Error inesperado", dict(rechazados)["R1_LAB-24001.pdf"])
        self.assertTrue((self.carpeta / "rechazados" / "R1_LAB-24001.json").exists())

    def test_avance_y_panel_por_etapa(self):
        call_command("cargar_demo", "--a-bandeja", verbosity=0)
        servicios.importar_bandeja(self.lab)
        r1 = Resultado.objects.get(folio_laboratorio="LAB-24001")
        r5 = Resultado.objects.get(folio_laboratorio="LAB-24005")
        servicios.asociar(r1, Paciente.objects.get(folio_expediente="EIRA-0001"), self.eira)
        servicios.devolver(r5, self.eira, "Escaneo ilegible")
        self.assertEqual([p["estado"] for p in r1.pasos][:3], ["hecho", "hecho", "actual"])
        self.assertEqual(r1.responsable, "EIRA")
        self.assertEqual([p["estado"] for p in r5.pasos][:2], ["hecho", "devuelto"])

        ind = servicios.indicadores_panel()
        etapas = {e["clave"]: e["n"] for e in ind["etapas"]}
        self.assertEqual((etapas["por_asociar"], etapas["en_revision"], etapas["devueltos"]), (3, 1, 1))
        self.assertEqual((ind["total"], ind["en_proceso"]), (5, 4))

        self.client.login(username="admin@eira.test", password="Demo2026!")
        respuesta = self.client.get(reverse("panel"), {"etapa": "devueltos"})
        self.assertContains(respuesta, "LAB-24005")
        self.assertNotContains(respuesta, "LAB-24001")
