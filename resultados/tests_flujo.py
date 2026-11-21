"""Contratos de seguridad del flujo real; las brechas no se ocultan como éxitos."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from . import servicios as s
from .models import Estado, EventoBitacora, Notificacion, Paciente, Resultado, Rol, Usuario


class EscenariosFlujo(TestCase):
    def setUp(self):
        carpeta = tempfile.TemporaryDirectory()
        self.addCleanup(carpeta.cleanup)
        self.carpeta = Path(carpeta.name)
        ajustes = override_settings(MEDIA_ROOT=self.carpeta / "privado",
                                    CARPETA_ENTRADA=self.carpeta, SEGUNDOS_ESPERA_BANDEJA=0)
        ajustes.enable()
        self.addCleanup(ajustes.disable)
        self.p = Paciente.objects.create(nombre="María Pérez", fecha_nacimiento="1990-01-01",
                                         folio_expediente="E-1", correo="maria@example.test", telefono="5551234567")
        self.p.refresh_from_db()
        self.lab = Usuario.objects.create_user(username="laboratorio", rol=Rol.LABORATORIO)
        self.eira = Usuario.objects.create_user(username="administracion", rol=Rol.EIRA)
        self.medico = Usuario.objects.create_user(username="medico", rol=Rol.MEDICO)
        self.paciente = Usuario.objects.create_user(username="paciente", rol=Rol.PACIENTE, paciente=self.p)
        self.r = self.cargar()

    def cargar(self, usuario=None, contenido=b"%PDF-1.4\nDocumento sintetico\n%%EOF", folio="L-1"):
        return s.cargar_resultado(usuario or self.lab, SimpleUploadedFile("hoja.pdf", contenido),
                                  self.p.nombre, self.p.fecha_nacimiento, self.p.folio_expediente, folio)

    def revisar(self):
        s.asociar(self.r, self.p, self.eira)
        s.aprobar_revision(self.r, self.eira)

    def autorizar(self):
        self.revisar()
        s.autorizar(self.r, self.medico)

    def documento(self, usuario, ruta="documento"):
        self.client.force_login(usuario)
        respuesta = self.client.get(reverse(ruta, args=[self.r.pk]))
        respuesta.close()
        return respuesta.status_code

    def test_recorrido_completo(self):
        """Laboratorio/EIRA/médico/paciente: recorrido HTTP completo y descarga autenticada."""
        self.client.force_login(self.lab)
        respuesta = self.client.post(reverse("laboratorio"), {
            "archivo": SimpleUploadedFile("otro.pdf", b"%PDF-1.4\nSegundo documento"),
            "hoja_nombre": self.p.nombre, "hoja_fecha_nacimiento": "1990-01-01",
            "hoja_folio_expediente": "E-1", "folio_laboratorio": "L-2"})
        self.assertEqual(respuesta.status_code, 302)
        self.r = Resultado.objects.get(folio_laboratorio="L-2")
        for usuario, accion, datos, estado in [
            (self.eira, "asociar", {"paciente_id": self.p.pk}, Estado.ASOCIADO),
            (self.eira, "aprobar", {}, Estado.REVISADO),
            (self.medico, "autorizar", {}, Estado.AUTORIZADO),
            (self.eira, "notificar", {"canal": "correo"}, Estado.NOTIFICADO),
        ]:
            self.client.force_login(usuario)
            self.assertEqual(self.client.post(reverse("accion", args=[self.r.pk, accion]), datos).status_code, 302)
            self.r.refresh_from_db()
            self.assertEqual(self.r.estado, estado)
        self.assertEqual(self.documento(self.paciente, "descargar"), 200)
        self.r.refresh_from_db()
        self.assertEqual(self.r.estado, Estado.CONSULTADO)
        self.assertEqual(self.r.eventos.count(), 6)

    def test_homonimos(self):
        """EIRA: homónimos con fecha y expediente diferentes no se confunden."""
        otra = Paciente.objects.create(nombre=self.p.nombre, fecha_nacimiento="1992-01-01", folio_expediente="E-2")
        with self.assertRaises(s.ReglaNegocioError):
            s.asociar(self.r, otra, self.eira)
        s.asociar(self.r, self.p, self.eira)
        self.assertEqual(self.r.paciente, self.p)

    def test_identidad_no_coincide(self):
        """EIRA: un folio discrepante bloquea y audita la asociación."""
        self.r.hoja_folio_expediente = "OTRO"
        with self.assertRaises(s.ReglaNegocioError):
            s.asociar(self.r, self.p, self.eira)
        self.assertTrue(self.r.eventos.filter(accion="Asociación bloqueada").exists())

    def test_ilegible_devuelto(self):
        """EIRA: revisión humana devuelve escaneo ilegible con motivo."""
        s.devolver(self.r, self.eira, "Escaneo ilegible")
        self.assertEqual(self.r.estado, Estado.DEVUELTO)

    @unittest.expectedFailure
    def test_pdf_invalido_con_firma(self):
        """Laboratorio: BRECHA, la firma PDF no garantiza documento válido ni legible; validar contenido."""
        with self.assertRaises(s.ReglaNegocioError):
            self.cargar(contenido=b"%PDF-basura ilegible")

    @unittest.expectedFailure
    def test_varios_pacientes_pdf(self):
        """EIRA: BRECHA, falta control de varios pacientes por PDF; exigir revisión explícita."""
        self.assertIn("paciente_unico_verificado", {c.name for c in Resultado._meta.fields})

    @unittest.expectedFailure
    def test_duplicado_manual(self):
        """Laboratorio: BRECHA, carga manual repite hash y folio; deduplicar también fuera de bandeja."""
        with self.assertRaises(s.ReglaNegocioError):
            self.cargar()

    def test_salto_estado(self):
        """Médico: no puede autorizar desde cargado."""
        with self.assertRaises(s.ReglaNegocioError):
            s.autorizar(self.r, self.medico)
        self.r.refresh_from_db()
        self.assertEqual(self.r.estado, Estado.CARGADO)

    @unittest.expectedFailure
    def test_cargador_autoriza(self):
        """Médico: BRECHA, cargador con cambio de rol puede autorizar; separar carga y autorización."""
        self.revisar()
        self.lab.rol = Rol.MEDICO
        self.lab.save()
        with self.assertRaises(s.ReglaNegocioError):
            s.autorizar(self.r, self.lab)

    def test_revisor_no_autoriza(self):
        """EIRA/médico: la misma identidad revisora no autoriza aunque cambie de rol."""
        self.revisar()
        self.eira.rol = Rol.MEDICO
        with self.assertRaises(s.ReglaNegocioError):
            s.autorizar(self.r, self.eira)

    @unittest.expectedFailure
    def test_medico_no_asignado(self):
        """Médico: BRECHA, sin asignaciones puede leer y autorizar cualquier paciente; limitar alcance."""
        self.revisar()
        self.assertEqual(self.documento(self.medico), 404)

    def test_paciente_ajeno(self):
        """Paciente: documento ajeno responde 404 y deja auditoría de acceso denegado."""
        self.autorizar()
        otro = Usuario.objects.create_user(username="otro", rol=Rol.PACIENTE)
        self.assertEqual(self.documento(otro), 404)
        self.assertTrue(self.r.eventos.filter(accion="Acceso denegado al documento").exists())

    def test_sin_sesion(self):
        """Anónimo: el enlace exige sesión y no entrega un PDF público."""
        self.assertEqual(self.client.get(reverse("descargar", args=[self.r.pk])).status_code, 302)

    @unittest.expectedFailure
    def test_token_caducable(self):
        """Paciente: BRECHA, no existe token con vencimiento por descarga; solo sesión de 30 minutos."""
        self.assertTrue(callable(getattr(s, "emitir_token_descarga", None)))

    @unittest.expectedFailure
    def test_enlace_reutilizado(self):
        """Paciente: BRECHA, una URL autenticada puede descargarse repetidamente; falta uso único."""
        self.autorizar()
        self.assertEqual(self.documento(self.paciente, "descargar"), 200)
        self.assertEqual(self.documento(self.paciente, "descargar"), 404)

    @unittest.expectedFailure
    def test_aviso_diagnostico(self):
        """EIRA: BRECHA, plantilla alterada admite diagnóstico sin filtro; validar antes de guardar."""
        self.autorizar()
        with patch.object(s, "MENSAJE_AVISO", "Diagnóstico: cáncer; lesión LSIL"):
            with self.assertRaises(s.ReglaNegocioError):
                s.notificar(self.r, self.eira, "correo")

    def test_aviso_neutro(self):
        """EIRA: aviso predeterminado no revela hallazgos ni diagnóstico."""
        self.autorizar()
        s.notificar(self.r, self.eira, "sms")
        mensaje = self.r.notificaciones.get().mensaje.lower()
        for termino in ("diagnóstico", "lesión", "lsil", "cáncer", "papanicolaou"):
            self.assertNotIn(termino, mensaje)

    def test_sin_contacto_asistida(self):
        """EIRA: sin correo, teléfono ni cuenta activa se registra entrega asistida con identidad."""
        self.p.correo = ""
        self.p.telefono = ""
        self.p.save()
        self.paciente.is_active = False
        self.paciente.save()
        self.autorizar()
        for canal in ("correo", "sms"):
            with self.assertRaises(s.ReglaNegocioError):
                s.notificar(self.r, self.eira, canal)
        s.registrar_entrega_asistida(self.r, self.eira, "Paciente en recepción", "Documento de identidad")
        self.assertEqual(self.r.estado, Estado.ENTREGADO_ASISTIDO)

    @unittest.expectedFailure
    def test_falla_canal(self):
        """Sistema: BRECHA, no hay proveedor ni falla/fallback correo→SMS→asistida; solo simulación."""
        self.assertTrue(callable(getattr(s, "notificar_con_respaldo", None)))

    @unittest.expectedFailure
    def test_correccion_versionada(self):
        """EIRA: BRECHA, no existe versión/revocación ni reaviso; impedir acceso a versión anterior."""
        self.autorizar()
        self.assertTrue(callable(getattr(s, "corregir_resultado", None)))

    @unittest.expectedFailure
    def test_menor_tutor(self):
        """Tutor: BRECHA, no existe representación legal verificable ni rol de tutor; no compartir credenciales."""
        self.assertIn("tutor", Rol.values)

    def test_laboratorio_ajeno(self):
        """Laboratorio: otro usuario de laboratorio no puede acceder al documento."""
        otro = Usuario.objects.create_user(username="laboratorio_ajeno", rol=Rol.LABORATORIO)
        self.assertEqual(self.documento(otro), 404)
        self.assertEqual(self.documento(self.lab), 200)

    def test_bitacora_instancia(self):
        """EIRA: modificar o borrar una instancia de bitácora está bloqueado."""
        evento = self.r.eventos.first()
        with self.assertRaises(ValidationError):
            evento.save()
        with self.assertRaises(ValidationError):
            evento.delete()

    @unittest.expectedFailure
    def test_bitacora_actualizacion_masiva(self):
        """Sistema: BRECHA, QuerySet.update evita save y altera bitácora; proteger en base de datos."""
        evento = self.r.eventos.first()
        original = evento.detalle
        EventoBitacora.objects.filter(pk=evento.pk).update(detalle="alterado")
        evento.refresh_from_db()
        self.assertEqual(evento.detalle, original)

    @unittest.expectedFailure
    def test_denegacion_transicion_auditada(self):
        """Médico: BRECHA, saltos de estado denegados no dejan evento; auditar todos los rechazos."""
        cantidad = self.r.eventos.count()
        with self.assertRaises(s.ReglaNegocioError):
            s.autorizar(self.r, self.medico)
        self.assertEqual(self.r.eventos.count(), cantidad + 1)

    def test_bandeja_vacia(self):
        """Laboratorio: bandeja vacía no genera documentos ni rechazos."""
        self.assertEqual(s.importar_bandeja(self.lab), ([], []))

    def test_bandeja_sin_json(self):
        """Laboratorio: PDF sin datos se rechaza, archiva y audita."""
        (self.carpeta / "sin_datos.pdf").write_bytes(b"%PDF-1.4")
        cargados, rechazados = s.importar_bandeja(self.lab)
        self.assertEqual(cargados, [])
        self.assertIn("Falta", rechazados[0][1])
        self.assertTrue(EventoBitacora.objects.filter(accion="Importación rechazada").exists())

    def test_bandeja_duplicado(self):
        """Laboratorio: bandeja bloquea folio previamente cargado, a diferencia de carga manual."""
        (self.carpeta / "repetido.pdf").write_bytes(b"%PDF-1.4")
        (self.carpeta / "repetido.json").write_text(json.dumps({
            "nombre": self.p.nombre, "fecha_nacimiento": "1990-01-01",
            "folio_expediente": "E-1", "folio_laboratorio": "L-1"}))
        cargados, rechazados = s.importar_bandeja(self.lab)
        self.assertEqual(cargados, [])
        self.assertIn("ya fue cargado", rechazados[0][1])

    @unittest.expectedFailure
    def test_preferencia_asistida(self):
        """EIRA: BRECHA, preferencia asistida con cuenta activa no bloquea aviso digital; respetar elección."""
        self.p.preferencia_entrega = Paciente.Preferencia.ASISTIDA
        self.p.save()
        self.autorizar()
        with self.assertRaises(s.ReglaNegocioError):
            s.notificar(self.r, self.eira, "correo")
