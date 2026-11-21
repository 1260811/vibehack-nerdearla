"""Ejecuta contratos sobre una base de pruebas y publica evidencia reproducible."""
import io
import unittest
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.test.runner import DiscoverRunner


CONTRATOS_PENDIENTES = {
    "test_aviso_diagnostico": "Rechazar cualquier aviso con diagnóstico o hallazgos.",
    "test_bitacora_actualizacion_masiva": "Impedir cambios de bitácora también mediante ORM masivo.",
    "test_cargador_autoriza": "Impedir que la identidad cargadora autorice clínicamente.",
    "test_correccion_versionada": "Ofrecer corrección versionada, reaviso y revocación de la versión anterior.",
    "test_denegacion_transicion_auditada": "Registrar un evento incluso cuando se rechaza una transición.",
    "test_duplicado_manual": "Rechazar una segunda carga del mismo documento/folio.",
    "test_enlace_reutilizado": "Rechazar la reutilización de una descarga consumida.",
    "test_falla_canal": "Ofrecer respaldo ante falla de correo, después SMS y finalmente asistencia.",
    "test_medico_no_asignado": "Denegar lectura y autorización sin asignación médico-paciente.",
    "test_menor_tutor": "Disponer de representación legal verificable para menores.",
    "test_pdf_invalido_con_firma": "Rechazar contenido inválido aunque comience con firma PDF.",
    "test_preferencia_asistida": "Respetar la preferencia asistida aunque exista una cuenta activa.",
    "test_token_caducable": "Emitir tokens de descarga con caducidad independiente de la sesión.",
    "test_varios_pacientes_pdf": "Exigir control explícito de una sola paciente por documento.",
}


class ResultadoDocumentado(unittest.TextTestResult):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.filas = []

    def anotar(self, prueba, estado, obtenido):
        descripcion = prueba.shortDescription() or prueba.id()
        actor, _, escenario = descripcion.partition(": ")
        esperado, _, recomendacion = escenario.partition("; ")
        self.filas.append((esperado.replace("BRECHA, ", ""), actor,
                           CONTRATOS_PENDIENTES.get(prueba._testMethodName, esperado),
                           obtenido, estado, recomendacion or "Mantener esta protección y su prueba."))

    def addSuccess(self, prueba):
        super().addSuccess(prueba)
        self.anotar(prueba, "✅", "Contrato satisfecho en la aplicación real.")

    def addExpectedFailure(self, prueba, error):
        super().addExpectedFailure(prueba, error)
        observacion = prueba.shortDescription().partition("BRECHA, ")[2].partition("; ")[0]
        self.anotar(prueba, "❌", "Brecha reproducida: " + observacion + ".")

    def addFailure(self, prueba, error):
        super().addFailure(prueba, error)
        self.anotar(prueba, "❌", "Fallo no esperado: " + str(error[1]))

    def addError(self, prueba, error):
        super().addError(prueba, error)
        self.anotar(prueba, "❌", "Error de ejecución: " + str(error[1]))

    def addUnexpectedSuccess(self, prueba):
        super().addUnexpectedSuccess(prueba)
        self.anotar(prueba, "❌", "Éxito inesperado: revisar marca expectedFailure antes de cerrar la brecha.")


class EjecutorDocumentado(DiscoverRunner):
    def run_suite(self, suite, **kwargs):
        self.resultado_documentado = unittest.TextTestRunner(
            stream=self.stream, verbosity=2, resultclass=ResultadoDocumentado).run(suite)
        return self.resultado_documentado


class Command(BaseCommand):
    help = "Prueba el flujo real y escribe docs/casos_borde.md, sin usar datos de producción."

    def handle(self, *args, **options):
        salida = io.StringIO()
        ejecutor = EjecutorDocumentado(verbosity=0, interactive=False)
        ejecutor.stream = salida
        fallos = ejecutor.run_tests(["resultados.tests_flujo"])
        self.stdout.write(salida.getvalue())
        resultado = ejecutor.resultado_documentado
        documento = ["# Casos de borde del flujo real", "",
            "Generado con `python3 manage.py probar_flujo` sobre una base aislada de pruebas.", "",
            "✅ = contrato satisfecho; ❌ = brecha reproducida (fallo esperado), no una protección implementada.",
            "Los contratos de funciones/campos ausentes comprueban ausencia, no simulan una implementación.",
            "No se probaron proveedores reales, OCR, conectividad ni despliegue productivo.", "",
            f"Escenarios: {resultado.testsRun}. Brechas esperadas: {len(resultado.expectedFailures)}. "
            f"Fallos inesperados: {fallos}.", "",
            "| Escenario | Actor | Esperado | Obtenido | Estado | Riesgo/recomendación |",
            "|---|---|---|---|---|---|"]
        for fila in resultado.filas:
            documento.append("| " + " | ".join(str(c).replace("|", "\\|").replace("\n", " ") for c in fila) + " |")
        destino = Path(settings.BASE_DIR) / "docs" / "casos_borde.md"
        destino.parent.mkdir(exist_ok=True)
        destino.write_text("\n".join(documento) + "\n", encoding="utf-8")
        self.stdout.write(f"Informe generado: {destino.relative_to(settings.BASE_DIR)}")
        if fallos:
            raise CommandError("Hay fallos inesperados; revisar informe y salida de pruebas.")
