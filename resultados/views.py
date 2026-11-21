from datetime import date, timedelta
from functools import wraps

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.conf import settings
from django.http import FileResponse, Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from . import extractor, servicios
from .forms import CargaForm
from .models import Estado, EventoBitacora, Notificacion, Paciente, Resultado, Rol, duracion

INICIO_POR_ROL = {
    Rol.LABORATORIO: "laboratorio",
    Rol.EIRA: "panel",
    Rol.MEDICO: "medico",
}
SESION_ENLACES = "enlaces_verificados"


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
def extraer_hoja(request):
    """Propone los datos de la hoja; no guarda el archivo."""
    archivo = request.FILES.get("archivo")
    if archivo is None or archivo.size > settings.TAMANO_MAXIMO_PDF or archivo.read(5) != b"%PDF-":
        return JsonResponse({"error": "Selecciona un PDF válido de hasta 10 MB."}, status=400)
    archivo.seek(0)
    try:
        campos = extractor.extraer_datos(archivo)
    except extractor.ExtraccionError as e:
        return JsonResponse({"error": str(e)}, status=422)
    return JsonResponse({"campos": campos})


@require_POST
@rol_requerido(Rol.LABORATORIO, Rol.EIRA)
def importar_bandeja(request):
    cargados, rechazados = servicios.importar_bandeja(request.user)
    if not cargados and not rechazados:
        en_espera = len(servicios.pendientes_en_bandeja())
        messages.warning(request, (
            f"{en_espera} PDF(s) llegaron hace menos de {settings.SEGUNDOS_ESPERA_BANDEJA} s y pueden seguir "
            "copiándose; vuelve a importar en unos segundos."
        ) if en_espera else "La bandeja de entrada está vacía.")
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
    try:
        dia = date.fromisoformat(request.GET.get("dia", ""))
    except ValueError:
        dia = timezone.localdate()
    base = Resultado.objects.select_related("paciente")
    del_dia = base.filter(autorizado_en__date=dia)
    con_fallo = Notificacion.objects.filter(estado=Notificacion.Estado.FALLIDA).values("resultado")
    grupos = {
        "por_asociar": ("Por asociar", base.filter(estado=Estado.CARGADO)),
        "por_revisar": ("Por revisar", base.filter(estado=Estado.ASOCIADO)),
        "por_autorizar": ("Por autorizar", base.filter(estado=Estado.REVISADO)),
        "devueltos": ("Devueltos al laboratorio", base.filter(estado=Estado.DEVUELTO)),
        "sin_abrir": ("Avisadas sin abrir", del_dia.filter(estado=Estado.NOTIFICADO)),
        "reintentos": ("Con reintentos de aviso", del_dia.filter(pk__in=con_fallo)),
        "asistida": ("Requieren entrega asistida", del_dia.filter(
            requiere_entrega_asistida=True, estado__in=[Estado.AUTORIZADO, Estado.NOTIFICADO])),
        "entregados": ("Entregados", del_dia.filter(estado__in=[Estado.CONSULTADO, Estado.ENTREGADO_ASISTIDO])),
    }
    kpis = [{"clave": k, "etiqueta": etiqueta, "n": qs.count()} for k, (etiqueta, qs) in grupos.items()]
    entregados_dia = list(Resultado.objects.filter(entregado_en__date=dia).values_list("creado", "entregado_en"))
    promedio = (duracion(sum((fin - ini for ini, fin in entregados_dia), timedelta()) / len(entregados_dia))
                if entregados_dia else None)
    ver = request.GET.get("ver", "")
    if ver in grupos:
        titulo, resultados = grupos[ver]
    else:
        ver, titulo, resultados = "", "Todos los documentos", base
    contacto = Resultado.objects.filter(requiere_contacto=True).exclude(
        estado__in=[Estado.ENTREGADO_ASISTIDO, Estado.DEVUELTO]
    ).select_related("paciente")
    return render(request, "resultados/panel.html", {
        "dia": dia, "es_hoy": dia == timezone.localdate(), "ver": ver, "titulo": titulo,
        "pendientes": kpis[:4], "autorizados": kpis[4:], "total_autorizados": del_dia.count(),
        "promedio": promedio, "n_entregados_dia": len(entregados_dia),
        "resultados": resultados, "contacto": contacto,
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
        "notificaciones": resultado.notificaciones.order_by("-intento", "-creada"),
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
            aviso = servicios.autorizar(resultado, usuario, datos.get("requiere_contacto") == "on")
            if aviso:
                messages.success(request, f"Resultado autorizado. Aviso enviado automáticamente por {aviso.get_canal_display().lower()}.")
            else:
                messages.success(request, "Resultado autorizado. La paciente requiere entrega asistida.")
        elif nombre == "fallo":
            servicios.simular_fallo_aviso(resultado, usuario)
            messages.success(request, "Fallo de entrega simulado.")
        elif nombre == "reintentar":
            aviso = servicios.reintentar_aviso(resultado, usuario)
            messages.success(request, f"Aviso reenviado por {aviso.get_canal_display().lower()} (intento {aviso.intento}).")
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
    return _respuesta_pdf(resultado, descarga)


def _respuesta_pdf(resultado, descarga):
    respuesta = FileResponse(
        resultado.archivo.open("rb"), content_type="application/pdf",
        as_attachment=descarga, filename=f"resultado_{resultado.folio_laboratorio}.pdf",
    )
    respuesta["Cache-Control"] = "no-store"
    return respuesta


def acceso_paciente(request, token):
    enlace = servicios.buscar_enlace(token)
    if enlace is None or not enlace.vigente:
        return render(request, "resultados/acceso_invalido.html",
                      {"bloqueado": bool(enlace and enlace.bloqueado)}, status=404)
    clave_fecha = f"enlace_{enlace.pk}_fecha"
    verificado = enlace.pk in request.session.get(SESION_ENLACES, [])
    error = None
    if request.method == "POST" and not verificado:
        paso = request.POST.get("paso")
        if paso == "fecha":
            try:
                fecha = date.fromisoformat(request.POST.get("fecha_nacimiento", ""))
            except ValueError:
                error = "Escribe tu fecha de nacimiento completa."
            else:
                error = servicios.validar_fecha(enlace, fecha)
                if error is None:
                    request.session[clave_fecha] = True
        elif paso == "codigo" and request.session.get(clave_fecha):
            error = servicios.validar_codigo(enlace, request.POST.get("codigo"), request.META.get("REMOTE_ADDR", ""))
            if error is None:
                request.session[SESION_ENLACES] = request.session.get(SESION_ENLACES, []) + [enlace.pk]
                request.session.set_expiry(30 * 60)
            elif "venció" in error:
                request.session.pop(clave_fecha, None)
        enlace.refresh_from_db()
        if enlace.bloqueado:
            return render(request, "resultados/acceso_invalido.html", {"bloqueado": True}, status=403)
        if error is None:
            return redirect("acceso_paciente", token=token)
    if verificado:
        paso = "documento"
    elif request.session.get(clave_fecha) and enlace.codigo_hash:
        paso = "codigo"
    else:
        paso = "fecha"
    return render(request, "resultados/acceso_paciente.html", {
        "token": token, "enlace": enlace, "r": enlace.resultado, "paso": paso, "error": error,
        "destino_codigo": servicios.enmascarar(enlace.codigo_destino) if enlace.codigo_destino else "",
        "canal_codigo": Notificacion.Canal(enlace.codigo_canal).label if enlace.codigo_canal else "",
        "intentos_restantes": servicios.MAX_INTENTOS_VERIFICACION - enlace.intentos_fallidos,
    })


def documento_paciente(request, token, descarga=False):
    enlace = servicios.buscar_enlace(token)
    if enlace is None or not enlace.vigente or enlace.pk not in request.session.get(SESION_ENLACES, []):
        raise Http404
    resultado = enlace.resultado
    if not servicios.integridad_correcta(resultado):
        servicios.registrar(None, "Integridad fallida", resultado, detalle="El hash del archivo no coincide.")
        return HttpResponse("El documento no pasó la verificación de integridad.", status=409)
    servicios.registrar_acceso(None, resultado, descarga=descarga)
    return _respuesta_pdf(resultado, descarga)


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
