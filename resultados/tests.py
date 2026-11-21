import shutil
import tempfile

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
        self.assertEqual(r.estado, Estado.AUTORIZADO)
        self.assertTrue(r.requiere_entrega_asistida)
        self.assertFalse(Notificacion.objects.filter(resultado=r).exists())
        servicios.registrar_entrega_asistida(r, self.eira, "La paciente en recepción", "INE")
        self.assertEqual(r.estado, Estado.ENTREGADO_ASISTIDO)

    def test_reintentos_de_aviso_hasta_entrega_asistida(self):
        r = self.resultado("LAB-24001")
        self.llevar_a_autorizado(r, self.p1)
        with self.assertRaises(servicios.ReglaNegocioError):
            servicios.reintentar_aviso(r, self.eira)
        servicios.simular_fallo_aviso(r, self.eira)
        reintento = servicios.reintentar_aviso(r, self.eira)
        self.assertEqual((reintento.intento, reintento.canal), (2, Notificacion.Canal.SMS))
        r = self.resultado("LAB-24001")
        servicios.simular_fallo_aviso(r, self.eira)
        r.refresh_from_db()
        self.assertTrue(r.requiere_entrega_asistida)
        with self.assertRaises(servicios.ReglaNegocioError):
            servicios.reintentar_aviso(self.resultado("LAB-24001"), self.eira)
        self.assertEqual(r.le_toca, ("EIRA", "Entrega asistida"))

    def test_panel_por_secciones_y_dia(self):
        r = self.resultado("LAB-24001")
        self.llevar_a_autorizado(r, self.p1)
        servicios.registrar_acceso(r.paciente.usuario, r)
        self.client.login(username="admin@eira.test", password="Demo2026!")
        respuesta = self.client.get(reverse("panel"), {"ver": "entregados"})
        self.assertContains(respuesta, "Pendientes")
        self.assertContains(respuesta, "LAB-24001")
        self.assertNotContains(respuesta, "LAB-24002")
        self.assertIsNotNone(respuesta.context["promedio"])
        otro_dia = self.client.get(reverse("panel"), {"dia": "2020-01-01", "ver": "entregados"})
        self.assertNotContains(otro_dia, "LAB-24001")
        self.assertEqual(otro_dia.context["total_autorizados"], 0)

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
