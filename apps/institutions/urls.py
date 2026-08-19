from django.urls import path

from . import views


urlpatterns = [
    path("", views.cde_home, name="cde_home"),
    path("centros/<int:organization_pk>/", views.cde_detail, name="cde_detail"),
    path(
        "centros/<int:organization_pk>/periodos/nuevo/",
        views.cde_period_create,
        name="cde_period_create",
    ),
    path("periodos/<int:pk>/corregir/", views.cde_period_edit, name="cde_period_edit"),
    path("periodos/<int:pk>/documento/", views.cde_period_document, name="cde_period_document"),
    path(
        "periodos/<int:period_pk>/integrantes/nuevo/",
        views.cde_member_create,
        name="cde_member_create",
    ),
    path("integrantes/<int:pk>/corregir/", views.cde_member_edit, name="cde_member_edit"),
    path(
        "integrantes/<int:pk>/registrar-salida/",
        views.cde_member_departure,
        name="cde_member_departure",
    ),
    path("integrantes/<int:pk>/documento/", views.cde_member_document, name="cde_member_document"),
]
