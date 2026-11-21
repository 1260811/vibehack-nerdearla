import uuid

from django.contrib.auth.models import AbstractUser
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone
from django.utils.functional import cached_property


def ruta_archivo(instancia, nombre):
    return f"resultados/{uuid.uuid4().hex}.pdf"


class Rol(models.TextChoices):
    LABORATORIO = "laboratorio", "Laboratorio"
    EIRA = "eira", "EIRA (administración)"
    MEDICO = "medico", "Médico"
    PACIENTE = "paciente", "Paciente"


class Paciente(models.Model):
    class Preferencia(models.TextChoices):
        DIGITAL = "digital", "Digital"
        ASISTIDA = "asistida", "Asistida"

    nombre = models.CharField(max_length=150)
    fecha_nacimiento = models.DateField()
    folio_expediente = models.CharField(max_length=30, unique=True)
    correo = models.EmailField(blank=True, null=True)
    telefono = models.CharField(max_length=30, blank=True)
    preferencia_entrega = models.CharField(max_length=10, choices=Preferencia.choices, default=Preferencia.DIGITAL)

    def __str__(self):
        return f"{self.nombre} ({self.folio_expediente})"


class Usuario(AbstractUser):
    rol = models.CharField(max_length=15, choices=Rol.choices)
    paciente = models.OneToOneField(Paciente, null=True, blank=True, on_delete=models.PROTECT, related_name="usuario")


class Estado(models.TextChoices):
    CARGADO = "cargado", "Cargado"
    ASOCIADO = "asociado", "Asociado"
    REVISADO = "revisado", "Revisado"
    AUTORIZADO = "autorizado", "Autorizado"
    NOTIFICADO = "notificado", "Notificado"
    CONSULTADO = "consultado", "Consultado"
    ENTREGADO_ASISTIDO = "entregado_asistido", "Entrega asistida"
    DEVUELTO = "devuelto", "Devuelto"


def duracion(td):
    minutos = max(int(td.total_seconds() // 60), 0)
    dias, minutos = divmod(minutos, 60 * 24)
    horas, minutos = divmod(minutos, 60)
    partes = [f"{dias} d"] * bool(dias) + [f"{horas} h"] * bool(horas) + [f"{minutos} min"]
    return " ".join(partes[:2])


PASOS = ["Cargado", "Asociado", "Revisado", "Autorizado", "Notificado", "Entregado"]
PASOS_POR_ESTADO = {"cargado": 1, "asociado": 2, "revisado": 3, "autorizado": 4, "notificado": 5,
                    "consultado": 6, "entregado_asistido": 6}


class Resultado(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    archivo = models.FileField(upload_to=ruta_archivo)
    sha256 = models.CharField(max_length=64)

    hoja_nombre = models.CharField("Nombre en la hoja", max_length=150)
    hoja_fecha_nacimiento = models.DateField("Fecha de nacimiento en la hoja")
    hoja_folio_expediente = models.CharField("Folio de expediente en la hoja", max_length=30)
    folio_laboratorio = models.CharField(max_length=30)

    paciente = models.ForeignKey(Paciente, null=True, blank=True, on_delete=models.PROTECT, related_name="resultados")
    estado = models.CharField(max_length=20, choices=Estado.choices, default=Estado.CARGADO)
    requiere_contacto = models.BooleanField(default=False)
    motivo_devolucion = models.TextField(blank=True)
    entrega_asistida_detalle = models.TextField(blank=True)
    requiere_entrega_asistida = models.BooleanField(default=False)

    cargado_por = models.ForeignKey(Usuario, on_delete=models.PROTECT, related_name="cargas")
    asociado_por = models.ForeignKey(Usuario, null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    revisado_por = models.ForeignKey(Usuario, null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    autorizado_por = models.ForeignKey(Usuario, null=True, blank=True, on_delete=models.PROTECT, related_name="+")

    creado = models.DateTimeField(auto_now_add=True)
    actualizado = models.DateTimeField(auto_now=True)
    etapa_desde = models.DateTimeField(default=timezone.now)
    autorizado_en = models.DateTimeField(null=True, blank=True)
    entregado_en = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-creado"]

    def __str__(self):
        return f"{self.folio_laboratorio} · {self.get_estado_display()}"

    @property
    def completado(self):
        return self.estado in {Estado.CONSULTADO, Estado.ENTREGADO_ASISTIDO}

    @property
    def tiempo_en_etapa(self):
        return duracion(timezone.now() - self.etapa_desde)

    @property
    def tiempo_entrega(self):
        return duracion(self.entregado_en - self.creado) if self.entregado_en else ""

    @cached_property
    def ultimo_aviso(self):
        return self.notificaciones.order_by("-intento", "-creada").first()

    @cached_property
    def avance(self):
        devuelto = self.estado == Estado.DEVUELTO
        hechos = PASOS_POR_ESTADO.get(self.estado) or 1 + bool(self.asociado_por_id) + bool(self.revisado_por_id)
        segmentos = []
        for i, nombre in enumerate(PASOS):
            if i < hechos:
                clase = "hecho"
            elif i == hechos:
                clase = "error" if devuelto else "actual"
            else:
                clase = "pendiente"
            segmentos.append({"nombre": nombre, "clase": clase})
        if self.estado == Estado.ENTREGADO_ASISTIDO and self.ultimo_aviso is None:
            segmentos[4]["clase"] = "omitido"
        return {"segmentos": segmentos, "hechos": sum(s["clase"] == "hecho" for s in segmentos), "total": len(PASOS)}

    @cached_property
    def le_toca(self):
        e = self.estado
        if self.requiere_entrega_asistida and e in {Estado.AUTORIZADO, Estado.NOTIFICADO}:
            return ("EIRA", "Entrega asistida")
        if e == Estado.NOTIFICADO and self.ultimo_aviso and self.ultimo_aviso.estado == Notificacion.Estado.FALLIDA:
            return ("EIRA", "Reintentar aviso")
        return {
            Estado.CARGADO: ("EIRA", "Asociar con expediente"),
            Estado.ASOCIADO: ("EIRA", "Revisión administrativa"),
            Estado.REVISADO: ("Médico", "Autorización clínica"),
            Estado.AUTORIZADO: ("Sistema", "Enviar aviso"),
            Estado.NOTIFICADO: ("Paciente", "Consultar el documento"),
            Estado.DEVUELTO: ("Laboratorio", "Corregir y volver a cargar"),
        }.get(e, ("", "Completado"))


class Notificacion(models.Model):
    class Canal(models.TextChoices):
        CORREO = "correo", "Correo"
        SMS = "sms", "SMS"

    class Estado(models.TextChoices):
        ENVIADA = "enviada", "Enviada (simulada)"
        FALLIDA = "fallida", "Falló la entrega (simulada)"

    resultado = models.ForeignKey(Resultado, on_delete=models.PROTECT, related_name="notificaciones")
    canal = models.CharField(max_length=10, choices=Canal.choices)
    destino = models.CharField(max_length=150)
    mensaje = models.TextField()
    estado = models.CharField(max_length=20, choices=Estado.choices, default=Estado.ENVIADA)
    intento = models.PositiveSmallIntegerField(default=1)
    creada = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-creada"]


class EventoBitacora(models.Model):
    """Registro de solo inserción: no se edita ni se borra."""

    resultado = models.ForeignKey(Resultado, null=True, blank=True, on_delete=models.PROTECT, related_name="eventos")
    usuario = models.ForeignKey(Usuario, null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    accion = models.CharField(max_length=80)
    estado_anterior = models.CharField(max_length=20, blank=True)
    estado_nuevo = models.CharField(max_length=20, blank=True)
    detalle = models.TextField(blank=True)
    fecha = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-fecha", "-id"]

    @property
    def etiqueta_anterior(self):
        return Estado(self.estado_anterior).label if self.estado_anterior else "—"

    @property
    def etiqueta_nueva(self):
        return Estado(self.estado_nuevo).label if self.estado_nuevo else "—"

    def save(self, *args, **kwargs):
        if self.pk is not None:
            raise ValidationError("La bitácora es de solo inserción.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("La bitácora es de solo inserción.")
