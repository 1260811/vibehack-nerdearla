"""Contratos de seguridad del flujo real; las brechas no se ocultan como éxitos."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from . import servicios as s
from .tests import ultimo_codigo, verificar_como_paciente
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

    def documento_paciente(self, ruta="descargar/"):
        self.client.logout()
        respuesta = self.client.get(verificar_como_paciente(self.client, self.r) + ruta)
        respuesta.close()
        return respuesta.status_code

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
            (self.medico, "autorizar", {}, Estado.NOTIFICADO),
        ]:
            self.client.force_login(usuario)
            self.assertEqual(self.client.post(reverse("accion", args=[self.r.pk, accion]), datos).status_code, 302)
            self.r.refresh_from_db()
            self.assertEqual(self.r.estado, estado)
        self.assertEqual(self.documento_paciente(), 200)
        self.r.refresh_from_db()
        self.assertEqual(self.r.estado, Estado.CONSULTADO)
        # carga, asociación, revisión, autorización, aviso, código, acuse, consulta
        self.assertEqual(self.r.eventos.count(), 8)

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
        """Paciente: quien solo tiene el enlace, sin fecha ni código, no ve el PDF; el error queda auditado."""
        self.autorizar()
        ruta = self.r.ultimo_aviso.enlace_simulado
        self.assertEqual(self.client.get(ruta + "documento/").status_code, 404)
        self.client.post(ruta, {"paso": "fecha", "fecha_nacimiento": "1992-01-01"})
        self.assertEqual(self.client.get(ruta + "documento/").status_code, 404)
        self.assertTrue(self.r.eventos.filter(accion="Verificación fallida").exists())

    def test_sin_sesion(self):
        """Anónimo: la ruta interna del personal exige inicio de sesión, no sustituye al enlace de paciente."""
        self.assertEqual(self.client.get(reverse("descargar", args=[self.r.pk])).status_code, 302)

    def test_token_caducable(self):
        """Paciente: el enlace del aviso vence a las 72 horas y deja de abrir."""
        self.autorizar()
        enlace = self.r.enlaces.get()
        self.assertAlmostEqual((enlace.expira - enlace.creado).total_seconds(), s.VIGENCIA_ENLACE.total_seconds(), delta=5)
        self.r.enlaces.update(expira=s.timezone.now())
        self.assertEqual(self.client.get(self.r.ultimo_aviso.enlace_simulado).status_code, 404)

    @unittest.expectedFailure
    def test_enlace_reutilizado(self):
        """Paciente: BRECHA, tras verificar, el PDF se puede volver a descargar mientras dure la sesión (30 min)."""
        self.autorizar()
        self.assertEqual(self.documento_paciente(), 200)
        respuesta = self.client.get(self.r.ultimo_aviso.enlace_simulado + "descargar/")
        respuesta.close()
        self.assertEqual(respuesta.status_code, 404)

    @unittest.expectedFailure
    def test_aviso_diagnostico(self):
        """EIRA: BRECHA, plantilla alterada admite diagnóstico sin filtro; validar antes de guardar."""
        self.revisar()
        with patch.object(s, "MENSAJE_AVISO", "Diagnóstico: cáncer; lesión LSIL"):
            with self.assertRaises(s.ReglaNegocioError):
                s.autorizar(self.r, self.medico)

    def test_aviso_neutro(self):
        """EIRA: aviso predeterminado no revela hallazgos ni diagnóstico."""
        self.autorizar()
        mensaje = self.r.notificaciones.get().mensaje.lower()
        for termino in ("diagnóstico", "lesión", "lsil", "cáncer", "papanicolaou"):
            self.assertNotIn(termino, mensaje)

    def test_sin_contacto_asistida(self):
        """EIRA: sin correo ni teléfono se registra entrega asistida con identidad."""
        self.p.correo = ""
        self.p.telefono = ""
        self.p.save()
        self.revisar()
        self.assertIsNone(s.autorizar(self.r, self.medico))
        self.assertTrue(self.r.requiere_entrega_asistida)
        self.assertFalse(self.r.notificaciones.exists())
        s.registrar_entrega_asistida(self.r, self.eira, "Paciente en recepción", "Documento de identidad")
        self.assertEqual(self.r.estado, Estado.ENTREGADO_ASISTIDO)

    @unittest.expectedFailure
    def test_falla_canal(self):
        """Sistema: BRECHA, el respaldo correo→SMS→asistida es simulado; falta proveedor real que reporte fallas."""
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

    def test_preferencia_asistida(self):
        """EIRA: la preferencia de entrega asistida se respeta aunque haya correo y teléfono."""
        self.p.preferencia_entrega = Paciente.Preferencia.ASISTIDA
        self.p.save()
        self.autorizar()
        self.assertTrue(self.r.requiere_entrega_asistida)
        self.assertFalse(self.r.notificaciones.exists())

    def pedir_codigo(self, cliente=None):
        cliente = cliente or self.client
        ruta = self.r.ultimo_aviso.enlace_simulado
        self.assertEqual(cliente.post(ruta, {"paso": "fecha", "fecha_nacimiento": "1990-01-01"}).status_code, 302)
        return ruta, ultimo_codigo(self.r)

    def test_fecha_incorrecta(self):
        """Paciente: fecha incorrecta no emite código, deniega PDF y registra un intento."""
        self.autorizar()
        ruta = self.r.ultimo_aviso.enlace_simulado
        self.client.post(ruta, {"paso": "fecha", "fecha_nacimiento": "1992-01-01"})
        self.assertFalse(self.r.notificaciones.filter(tipo=Notificacion.Tipo.CODIGO).exists())
        self.assertEqual(self.r.enlaces.get().intentos_fallidos, 1)
        self.assertEqual(self.client.get(ruta + "documento/").status_code, 404)

    def test_codigo_incorrecto(self):
        """Paciente: código incorrecto no acredita identidad ni entrega documento."""
        self.autorizar()
        ruta, codigo = self.pedir_codigo()
        incorrecto = "000000" if codigo != "000000" else "111111"
        self.client.post(ruta, {"paso": "codigo", "codigo": incorrecto})
        self.assertEqual(self.client.get(ruta + "documento/").status_code, 404)
        self.assertEqual(self.r.enlaces.get().intentos_fallidos, 1)
        self.assertFalse(self.r.eventos.filter(accion="Acuse de recibo de la paciente").exists())

    def test_fuerza_bruta_otras_sesiones(self):
        """Paciente: tres errores repartidos entre sesiones bloquean el enlace y requieren asistencia."""
        self.autorizar()
        ruta = self.r.ultimo_aviso.enlace_simulado
        for intento in range(s.MAX_INTENTOS_VERIFICACION):
            respuesta = Client().post(ruta, {"paso": "fecha", "fecha_nacimiento": "1992-01-01"})
            self.assertEqual(respuesta.status_code, 403 if intento == 2 else 200)
        self.r.refresh_from_db()
        self.assertTrue(self.r.requiere_entrega_asistida)
        self.assertTrue(self.r.enlaces.get().bloqueado)
        self.assertEqual(Client().get(ruta).status_code, 404)
        self.assertEqual(self.r.eventos.filter(accion="Verificación fallida").count(), 3)

    def test_codigo_sin_fecha(self):
        """Paciente: conocer el código sin validar fecha en esa sesión no abre el documento."""
        self.autorizar()
        ruta, codigo = self.pedir_codigo()
        otro = Client()
        otro.post(ruta, {"paso": "codigo", "codigo": codigo})
        self.assertEqual(otro.get(ruta + "documento/").status_code, 404)

    def test_codigo_caducado(self):
        """Paciente: código caducado se rechaza aunque el enlace siga vigente."""
        self.autorizar()
        ruta, codigo = self.pedir_codigo()
        self.r.enlaces.update(codigo_expira=s.timezone.now() - s.VIGENCIA_CODIGO)
        respuesta = self.client.post(ruta, {"paso": "codigo", "codigo": codigo})
        self.assertContains(respuesta, "El código venció")
        self.assertEqual(self.client.get(ruta + "documento/").status_code, 404)

    def test_codigo_rotado(self):
        """Paciente: al solicitar otro código el anterior deja de ser válido."""
        self.autorizar()
        with patch.object(s.secrets, "randbelow", side_effect=[123456, 654321]):
            ruta, anterior = self.pedir_codigo()
            self.pedir_codigo()
        self.client.post(ruta, {"paso": "codigo", "codigo": anterior})
        self.assertEqual(self.client.get(ruta + "documento/").status_code, 404)
        self.client.post(ruta, {"paso": "codigo", "codigo": "654321"})
        respuesta = self.client.get(ruta + "documento/")
        respuesta.close()
        self.assertEqual(respuesta.status_code, 200)

    def test_enlace_otro_expediente(self):
        """Paciente: verificar un enlace no habilita el enlace de otra paciente ni su PDF."""
        self.autorizar()
        verificar_como_paciente(self.client, self.r)
        otra = Paciente.objects.create(nombre="Ana Gómez", fecha_nacimiento="1980-02-02", folio_expediente="E-2",
                                        correo="ana@example.test")
        otra.refresh_from_db()
        otro = s.cargar_resultado(self.lab, SimpleUploadedFile("otra.pdf", b"%PDF-1.4 Otra paciente"),
                                  otra.nombre, otra.fecha_nacimiento, otra.folio_expediente, "L-2")
        s.asociar(otro, otra, self.eira)
        s.aprobar_revision(otro, self.eira)
        s.autorizar(otro, self.medico)
        ruta = otro.ultimo_aviso.enlace_simulado
        self.assertEqual(self.client.get(ruta + "documento/").status_code, 404)
        self.client.post(ruta, {"paso": "fecha", "fecha_nacimiento": self.p.fecha_nacimiento.isoformat()})
        self.assertFalse(otro.notificaciones.filter(tipo=Notificacion.Tipo.CODIGO).exists())

    def test_antes_autorizacion(self):
        """Paciente: antes de autorizar no existe enlace emitido y un identificador de resultado no sirve como token."""
        self.revisar()
        self.assertFalse(self.r.enlaces.exists())
        self.assertFalse(self.r.notificaciones.exists())
        ruta = reverse("acceso_paciente", args=[str(self.r.pk)])
        self.assertEqual(self.client.get(ruta).status_code, 404)
        self.assertEqual(self.client.get(ruta + "documento/").status_code, 404)

    def test_aviso_separa_codigo(self):
        """Sistema: el aviso contiene enlace pero no código, enviado aparte por SMS si el aviso fue por correo."""
        self.autorizar()
        ruta, codigo = self.pedir_codigo()
        aviso = self.r.ultimo_aviso
        verificacion = self.r.notificaciones.get(tipo=Notificacion.Tipo.CODIGO)
        self.assertIn(ruta, aviso.mensaje)
        self.assertNotIn(codigo, aviso.mensaje)
        self.assertNotIn(ruta, verificacion.mensaje)
        self.assertEqual((aviso.canal, verificacion.canal), ("correo", "sms"))

    def test_enlace_caducado_sesion_verificada(self):
        """Paciente: enlace caducado deniega también el PDF de una sesión previamente verificada."""
        self.autorizar()
        ruta = verificar_como_paciente(self.client, self.r)
        self.r.enlaces.update(expira=s.timezone.now())
        self.assertEqual(self.client.get(ruta + "documento/").status_code, 404)

    def test_reintento_revoca_anterior(self):
        """EIRA: reintento de aviso cambia a SMS y revoca el enlace anterior incluso ya verificado."""
        self.autorizar()
        ruta = verificar_como_paciente(self.client, self.r)
        s.simular_fallo_aviso(self.r, self.eira)
        nuevo = s.reintentar_aviso(self.r, self.eira)
        self.assertEqual(nuevo.canal, "sms")
        self.assertEqual(self.client.get(ruta + "documento/").status_code, 404)
        self.assertEqual(self.client.get(nuevo.enlace_simulado).status_code, 200)

    def test_fallback_simulado(self):
        """Sistema/EIRA: dos fallas simuladas correo y SMS derivan a entrega asistida y revocación."""
        self.autorizar()
        s.simular_fallo_aviso(self.r, self.eira)
        aviso = s.reintentar_aviso(self.r, self.eira)
        self.assertEqual(aviso.canal, "sms")
        s.simular_fallo_aviso(self.r, self.eira)
        self.assertTrue(self.r.requiere_entrega_asistida)
        with self.assertRaises(s.ReglaNegocioError):
            s.reintentar_aviso(self.r, self.eira)
        s.registrar_entrega_asistida(self.r, self.eira, "Paciente", "Identificación")
        self.assertEqual(self.client.get(aviso.enlace_simulado).status_code, 404)

    @unittest.expectedFailure
    def test_fecha_malformada_limite(self):
        """Paciente: BRECHA, fechas vacías o malformadas no consumen intentos ni se auditan; limitar también entradas inválidas."""
        self.autorizar()
        ruta = self.r.ultimo_aviso.enlace_simulado
        for _ in range(s.MAX_INTENTOS_VERIFICACION):
            self.client.post(ruta, {"paso": "fecha", "fecha_nacimiento": ""})
        self.assertTrue(self.r.enlaces.get().bloqueado)

    @unittest.expectedFailure
    def test_reenvio_codigo_limite(self):
        """Paciente: BRECHA, solicitudes repetidas con fecha correcta generan códigos sin límite; limitar frecuencia y evitar abuso del canal."""
        self.autorizar()
        for _ in range(5):
            self.pedir_codigo()
        self.assertLessEqual(self.r.notificaciones.filter(tipo=Notificacion.Tipo.CODIGO).count(), 3)
