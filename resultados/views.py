from functools import wraps

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.conf import settings
from django.http import FileResponse, Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from . import servicios
from .forms import CargaForm
from .models import Estado, EventoBitacora, Notificacion, Paciente, Resultado, Rol

INICIO_POR_ROL = {
    Rol.LABORATORIO: "laboratorio",
    Rol.EIRA: "panel",
    Rol.MEDICO: "medico",
    Rol.PACIENTE: "mis_resultados",
}


def rol_requerido(*roles):
    def decorador(vista):
        @login_required
        @wraps(vista)
        def envoltura(request, *args, **kwargs):
            if request.user.rol not in roles:
                raise PermissionDenied
            return vista(request, *args, **kwargs)
        return envoltura
    return decorador


@login_required
def inicio(request):
    destino = INICIO_POR_ROL.get(request.user.rol)
    if destino is None:
        raise PermissionDenied
    return redirect(destino)


@rol_requerido(Rol.LABORATORIO, Rol.EIRA)
def laboratorio(request):
    form = CargaForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        try:
            r = servicios.cargar_resultado(request.user, **form.cleaned_data)
        except servicios.ReglaNegocioError as e:
            messages.error(request, str(e))
        else:
            messages.success(request, f"Documento {r.folio_laboratorio} cargado. EIRA lo asociará con el expediente.")
            return redirect("laboratorio")
    cargas = Resultado.objects.filter(cargado_por=request.user)
    return render(request, "resultados/laboratorio.html", {
        "form": form, "cargas": cargas,
        "en_bandeja": servicios.pendientes_en_bandeja(), "carpeta_entrada": settings.CARPETA_ENTRADA,
    })


@require_POST
@rol_requerido(Rol.LABORATORIO, Rol.EIRA)
def importar_bandeja(request):
    cargados, rechazados = servicios.importar_bandeja(request.user)
    if not cargados and not rechazados:
        messages.warning(request, "La bandeja de entrada está vacía.")
    if cargados:
        messages.success(request, f"{len(cargados)} documento(s) importado(s) desde la bandeja: "
                                  + ", ".join(r.folio_laboratorio for r in cargados) + ".")
    for nombre, motivo in rechazados:
        messages.error(request, f"{nombre} rechazado: {motivo}")
    return redirect("laboratorio")


def _con_avance(consulta):
    return consulta.select_related("paciente").prefetch_related("notificaciones")


@rol_requerido(Rol.EIRA, Rol.MEDICO)
def panel(request):
    filtro = request.GET.get("etapa", "")
    estados = servicios.estados_de_etapa(filtro)
    resultados = _con_avance(Resultado.objects.all())
    if estados:
        resultados = resultados.filter(estado__in=estados)
    else:
        filtro = ""
    contacto = Resultado.objects.filter(requiere_contacto=True).exclude(
        estado__in=[Estado.ENTREGADO_ASISTIDO, Estado.DEVUELTO]
    ).select_related("paciente")
    return render(request, "resultados/panel.html", {
        "ind": servicios.indicadores_panel(), "resultados": resultados, "filtro": filtro, "contacto": contacto,
    })


@rol_requerido(Rol.MEDICO)
def medico(request):
    return render(request, "resultados/medico.html", {
        "pendientes": _con_avance(Resultado.objects.filter(estado=Estado.REVISADO)),
        "autorizados": _con_avance(Resultado.objects.filter(autorizado_por=request.user))[:20],
    })


@rol_requerido(Rol.EIRA, Rol.MEDICO)
def detalle(request, pk):
    resultado = get_object_or_404(Resultado.objects.select_related("paciente"), pk=pk)
    contexto = {
        "r": resultado,
        "eventos": resultado.eventos.select_related("usuario"),
        "notificaciones": resultado.notificaciones.all(),
        "es_eira": request.user.rol == Rol.EIRA,
        "es_medico": request.user.rol == Rol.MEDICO,
    }
    if resultado.estado == Estado.CARGADO and request.user.rol == Rol.EIRA:
        contexto["candidatos"] = servicios.candidatos(resultado)
    if resultado.paciente:
        contexto["acceso_digital"] = servicios.tiene_acceso_digital(resultado.paciente)
    return render(request, "resultados/detalle.html", contexto)


@require_POST
@rol_requerido(Rol.EIRA, Rol.MEDICO)
def accion(request, pk, nombre):
    resultado = get_object_or_404(Resultado, pk=pk)
    usuario, datos = request.user, request.POST
    try:
        if nombre == "asociar":
            paciente = get_object_or_404(Paciente, pk=datos.get("paciente_id"))
            servicios.asociar(resultado, paciente, usuario)
            messages.success(request, "Documento asociado al expediente.")
        elif nombre == "aprobar":
            servicios.aprobar_revision(resultado, usuario)
            messages.success(request, "Revisión aprobada. Pasa a autorización clínica.")
        elif nombre == "devolver":
            servicios.devolver(resultado, usuario, datos.get("motivo"))
            messages.success(request, "Documento devuelto.")
        elif nombre == "autorizar":
            servicios.autorizar(resultado, usuario, datos.get("requiere_contacto") == "on")
            messages.success(request, "Resultado autorizado.")
        elif nombre == "notificar":
            servicios.notificar(resultado, usuario, datos.get("canal"))
            messages.success(request, "Aviso simulado enviado. Revisa la bandeja de avisos.")
        elif nombre == "entrega":
            servicios.registrar_entrega_asistida(resultado, usuario, datos.get("receptor"), datos.get("verificacion"))
            messages.success(request, "Entrega asistida registrada.")
        else:
            raise Http404
    except servicios.ReglaNegocioError as e:
        messages.error(request, str(e))
    return redirect("detalle", pk=pk)


@login_required
def documento(request, pk, descarga=False):
    resultado = get_object_or_404(Resultado, pk=pk)
    # Se responde 404 (no 403) para no revelar que el documento existe.
    if not servicios.puede_ver_documento(request.user, resultado):
        servicios.registrar(request.user, "Acceso denegado al documento", resultado)
        raise Http404
    if not servicios.integridad_correcta(resultado):
        servicios.registrar(request.user, "Integridad fallida", resultado, detalle="El hash del archivo no coincide.")
        return HttpResponse("El documento no pasó la verificación de integridad.", status=409)
    servicios.registrar_acceso(request.user, resultado, descarga=descarga)
    respuesta = FileResponse(
        resultado.archivo.open("rb"), content_type="application/pdf",
        as_attachment=descarga, filename=f"resultado_{resultado.folio_laboratorio}.pdf",
    )
    respuesta["Cache-Control"] = "no-store"
    return respuesta


@rol_requerido(Rol.PACIENTE)
def mis_resultados(request):
    resultados = Resultado.objects.filter(
        paciente_id=request.user.paciente_id, estado__in=servicios.ESTADOS_VISIBLES_PACIENTE
    )
    return render(request, "resultados/mis_resultados.html", {"resultados": resultados})


@rol_requerido(Rol.PACIENTE)
def ver_resultado(request, pk):
    resultado = get_object_or_404(Resultado, pk=pk)
    if not servicios.puede_ver_documento(request.user, resultado):
        raise Http404
    return render(request, "resultados/ver_resultado.html", {"r": resultado})


@rol_requerido(Rol.EIRA, Rol.MEDICO)
def avisos(request):
    return render(request, "resultados/avisos.html", {
        "avisos": Notificacion.objects.select_related("resultado", "resultado__paciente"),
    })


@rol_requerido(Rol.EIRA, Rol.MEDICO)
def bitacora(request):
    return render(request, "resultados/bitacora.html", {
        "eventos": EventoBitacora.objects.select_related("usuario", "resultado")[:300],
    })
