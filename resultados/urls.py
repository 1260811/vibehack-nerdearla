from django.contrib.auth import views as auth_views
from django.urls import path

from . import views

urlpatterns = [
    path("", views.inicio, name="inicio"),
    path("entrar/", auth_views.LoginView.as_view(template_name="resultados/login.html"), name="login"),
    path("salir/", auth_views.LogoutView.as_view(), name="logout"),
    path("laboratorio/", views.laboratorio, name="laboratorio"),
    path("panel/", views.panel, name="panel"),
    path("medico/", views.medico, name="medico"),
    path("resultados/<uuid:pk>/", views.detalle, name="detalle"),
    path("resultados/<uuid:pk>/accion/<slug:nombre>/", views.accion, name="accion"),
    path("resultados/<uuid:pk>/documento/", views.documento, name="documento"),
    path("resultados/<uuid:pk>/descargar/", views.documento, {"descarga": True}, name="descargar"),
    path("mis-resultados/", views.mis_resultados, name="mis_resultados"),
    path("mis-resultados/<uuid:pk>/", views.ver_resultado, name="ver_resultado"),
    path("avisos/", views.avisos, name="avisos"),
    path("bitacora/", views.bitacora, name="bitacora"),
]
