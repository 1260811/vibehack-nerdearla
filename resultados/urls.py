from django.contrib.auth import views as auth_views
from django.urls import path

from . import views

urlpatterns = [
    path("", views.inicio, name="inicio"),
    path("entrar/", auth_views.LoginView.as_view(template_name="resultados/login.html"), name="login"),
    path("salir/", auth_views.LogoutView.as_view(), name="logout"),
    path("laboratorio/", views.laboratorio, name="laboratorio"),
    path("laboratorio/extraer/", views.extraer_hoja, name="extraer_hoja"),
    path("laboratorio/importar-bandeja/", views.importar_bandeja, name="importar_bandeja"),
    path("panel/", views.panel, name="panel"),
    path("medico/", views.medico, name="medico"),
    path("resultados/<uuid:pk>/", views.detalle, name="detalle"),
    path("resultados/<uuid:pk>/accion/<slug:nombre>/", views.accion, name="accion"),
    path("resultados/<uuid:pk>/documento/", views.documento, name="documento"),
    path("resultados/<uuid:pk>/descargar/", views.documento, {"descarga": True}, name="descargar"),
    path("acceso/<str:token>/", views.acceso_paciente, name="acceso_paciente"),
    path("acceso/<str:token>/documento/", views.documento_paciente, name="documento_paciente"),
    path("acceso/<str:token>/descargar/", views.documento_paciente, {"descarga": True}, name="descargar_paciente"),
    path("avisos/", views.avisos, name="avisos"),
    path("bitacora/", views.bitacora, name="bitacora"),
]
