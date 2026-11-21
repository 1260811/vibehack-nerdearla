import uuid

from django.contrib.auth.models import AbstractUser
from django.core.exceptions import ValidationError
from django.db import models


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

    cargado_por = models.ForeignKey(Usuario, on_delete=models.PROTECT, related_name="cargas")
    asociado_por = models.ForeignKey(Usuario, null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    revisado_por = models.ForeignKey(Usuario, null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    autorizado_por = models.ForeignKey(Usuario, null=True, blank=True, on_delete=models.PROTECT, related_name="+")

    creado = models.DateTimeField(auto_now_add=True)
    actualizado = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-creado"]

    def __str__(self):
        return f"{self.folio_laboratorio} · {self.get_estado_display()}"


class Notificacion(models.Model):
    class Canal(models.TextChoices):
        CORREO = "correo", "Correo"
        SMS = "sms", "SMS"

    resultado = models.ForeignKey(Resultado, on_delete=models.PROTECT, related_name="notificaciones")
    canal = models.CharField(max_length=10, choices=Canal.choices)
    destino = models.CharField(max_length=150)
    mensaje = models.TextField()
    estado = models.CharField(max_length=20, default="simulada")
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
