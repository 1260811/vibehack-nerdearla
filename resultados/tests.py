import json
import os
import re
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


def ultimo_codigo(resultado):
    aviso = resultado.notificaciones.filter(tipo=Notificacion.Tipo.CODIGO).order_by("-creada", "-id").first()
    return re.search(r"\d{6}", aviso.mensaje).group()


def verificar_como_paciente(client, resultado, fecha=None, codigo=None):
    """Recorre el enlace del último aviso como lo haría la paciente. Devuelve la ruta del enlace."""
    ruta = resultado.ultimo_aviso.enlace_simulado
    fecha = fecha or resultado.paciente.fecha_nacimiento.isoformat()
    client.post(ruta, {"paso": "fecha", "fecha_nacimiento": fecha})
    client.post(ruta, {"paso": "codigo", "codigo": codigo or ultimo_codigo(resultado)})
    return ruta


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

        ruta = verificar_como_paciente(self.client, r)
        respuesta = self.client.get(ruta + "documento/")
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
        copia_vieja = Resultado.objects.get(pk=r.pk)
        servicios.registrar_acceso(None, r)
        servicios.registrar_acceso(None, copia_vieja, descarga=True)
        self.assertEqual(copia_vieja.estado, Estado.CONSULTADO)
        self.assertTrue(r.eventos.filter(accion="Descarga del documento por la paciente").exists())

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
        self.assertEqual(r.le_toca, ("Paciente", "Consultar el documento"))
        servicios.simular_fallo_aviso(r, self.eira)
        self.assertTrue(r.requiere_entrega_asistida)
        with self.assertRaises(servicios.ReglaNegocioError):
            servicios.reintentar_aviso(r, self.eira)
        self.assertEqual(r.notificaciones.count(), 2)
        self.assertEqual(r.le_toca, ("EIRA", "Entrega asistida"))

    def test_panel_por_secciones_y_dia(self):
        r = self.resultado("LAB-24001")
        self.llevar_a_autorizado(r, self.p1)
        servicios.registrar_acceso(None, r)
        self.client.login(username="admin@eira.test", password="Demo2026!")
        respuesta = self.client.get(reverse("panel"), {"ver": "entregados"})
        self.assertContains(respuesta, "Pendientes")
        self.assertContains(respuesta, "LAB-24001")
        self.assertNotContains(respuesta, "LAB-24002")
        self.assertIsNotNone(respuesta.context["promedio"])
        otro_dia = self.client.get(reverse("panel"), {"dia": "2020-01-01", "ver": "entregados"})
        self.assertNotContains(otro_dia, "LAB-24001")
        self.assertEqual(otro_dia.context["total_autorizados"], 0)

    def test_enlace_exige_fecha_y_codigo_y_no_abre_otro_resultado(self):
        r1, r2 = self.resultado("LAB-24001"), self.resultado("LAB-24002")
        servicios.asociar(r1, self.p1, self.eira)
        self.llevar_a_autorizado(r2, self.p2)
        ruta = r2.ultimo_aviso.enlace_simulado
        self.assertEqual(self.client.get(ruta + "documento/").status_code, 404)
        self.assertEqual(self.client.get(reverse("acceso_paciente", args=["inventado"])).status_code, 404)
        # La homónima P1 tiene el mismo nombre pero otra fecha: no recibe código.
        self.client.post(ruta, {"paso": "fecha", "fecha_nacimiento": self.p1.fecha_nacimiento.isoformat()})
        self.assertFalse(r2.notificaciones.filter(tipo=Notificacion.Tipo.CODIGO).exists())
        verificar_como_paciente(self.client, r2)
        self.assertEqual(self.client.get(ruta + "documento/").status_code, 200)
        self.assertEqual(self.client.get(reverse("documento", args=[r1.pk])).status_code, 302)
        self.assertEqual(self.client.get(reverse("panel")).status_code, 302)

    def test_codigo_llega_por_el_otro_canal_y_queda_acuse(self):
        r = self.resultado("LAB-24001")
        self.llevar_a_autorizado(r, self.p1)
        self.assertEqual(r.ultimo_aviso.canal, Notificacion.Canal.CORREO)
        self.assertNotIn(r.ultimo_aviso.enlace_simulado.split("/")[2], r.enlaces.get().token_hash)
        verificar_como_paciente(self.client, r)
        codigo = r.notificaciones.get(tipo=Notificacion.Tipo.CODIGO)
        self.assertEqual(codigo.canal, Notificacion.Canal.SMS)
        acuse = r.eventos.get(accion="Acuse de recibo de la paciente")
        self.assertIn("código por sms", acuse.detalle)

    def test_tres_intentos_fallidos_bloquean_y_piden_entrega_asistida(self):
        r = self.resultado("LAB-24001")
        self.llevar_a_autorizado(r, self.p1)
        ruta = r.ultimo_aviso.enlace_simulado
        self.client.post(ruta, {"paso": "fecha", "fecha_nacimiento": "2000-01-01"})
        self.client.post(ruta, {"paso": "fecha", "fecha_nacimiento": self.p1.fecha_nacimiento.isoformat()})
        self.client.post(ruta, {"paso": "codigo", "codigo": "000000" if ultimo_codigo(r) != "000000" else "111111"})
        respuesta = self.client.post(ruta, {"paso": "codigo", "codigo": "999999" if ultimo_codigo(r) != "999999" else "111111"})
        self.assertEqual(respuesta.status_code, 403)
        r.refresh_from_db()
        self.assertTrue(r.requiere_entrega_asistida)
        self.assertEqual(r.eventos.filter(accion="Verificación fallida").count(), 3)
        self.assertEqual(self.client.get(ruta).status_code, 404)

    def test_enlace_caduca_y_el_reintento_invalida_el_anterior(self):
        r = self.resultado("LAB-24001")
        self.llevar_a_autorizado(r, self.p1)
        primero = r.ultimo_aviso.enlace_simulado
        servicios.simular_fallo_aviso(r, self.eira)
        servicios.reintentar_aviso(r, self.eira)
        self.assertEqual(self.client.get(primero).status_code, 404)
        segundo = r.ultimo_aviso.enlace_simulado
        self.assertEqual(self.client.get(segundo).status_code, 200)
        r.enlaces.update(expira=servicios.timezone.now())
        self.assertEqual(self.client.get(segundo).status_code, 404)

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

    def test_archivo_ausente_no_se_entrega_al_personal(self):
        r = self.resultado("LAB-24001")
        archivo = Path(r.archivo.path)
        self.addCleanup(archivo.write_bytes, archivo.read_bytes())
        archivo.unlink()
        self.client.force_login(self.eira)
        for vista in ("documento", "descargar"):
            with self.subTest(vista=vista):
                eventos = r.eventos.count()
                respuesta = self.client.get(reverse(vista, args=[r.pk]))
                self.assertEqual(respuesta.status_code, 409)
                self.assertContains(respuesta, "verificación de integridad", status_code=409)
                self.assertEqual(r.eventos.count(), eventos + 1)
                self.assertTrue(r.eventos.filter(accion="Integridad fallida", usuario=self.eira).exists())
                self.assertEqual(r.eventos.latest("id").detalle, "El archivo no se encuentra en el almacén.")

    def test_archivo_ausente_no_se_entrega_a_la_paciente(self):
        r = self.resultado("LAB-24001")
        self.llevar_a_autorizado(r, self.p1)
        ruta = verificar_como_paciente(self.client, r)
        archivo = Path(r.archivo.path)
        self.addCleanup(archivo.write_bytes, archivo.read_bytes())
        archivo.unlink()
        for sufijo in ("documento/", "descargar/"):
            with self.subTest(sufijo=sufijo):
                eventos = r.eventos.count()
                respuesta = self.client.get(ruta + sufijo)
                self.assertEqual(respuesta.status_code, 409)
                self.assertContains(respuesta, "verificación de integridad", status_code=409)
                self.assertEqual(r.eventos.count(), eventos + 1)
                self.assertTrue(r.eventos.filter(accion="Integridad fallida", usuario__isnull=True).exists())
                self.assertEqual(r.eventos.latest("id").detalle, "El archivo no se encuentra en el almacén.")
                r.refresh_from_db()
                self.assertEqual(r.estado, Estado.NOTIFICADO)

    def test_archivo_alterado_no_se_entrega(self):
        r = self.resultado("LAB-24001")
        with open(r.archivo.path, "rb") as f:
            original = f.read()
        try:
            with open(r.archivo.path, "ab") as f:
                f.write(b"alterado")
            self.client.login(username="admin@eira.test", password="Demo2026!")
            self.assertEqual(self.client.get(reverse("documento", args=[r.pk])).status_code, 409)
            self.assertEqual(r.eventos.latest("id").detalle, "El hash del archivo no coincide.")
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
            self.client.login(username="laboratorio@lab.test", password="Demo2026!")
            respuesta = self.client.post(reverse("importar_bandeja"), follow=True)
            self.assertContains(respuesta, "pueden seguir copiándose")
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
