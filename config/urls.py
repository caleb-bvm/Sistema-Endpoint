from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path

from apps.accounts.views import RequiredPasswordChangeView


urlpatterns = [
    path("administracion/", admin.site.urls),
    path(
        "ingresar/",
        auth_views.LoginView.as_view(
            template_name="registration/login.html",
            redirect_authenticated_user=True,
        ),
        name="login",
    ),
    path("salir/", auth_views.LogoutView.as_view(), name="logout"),
    path("cambiar-contrasena/", RequiredPasswordChangeView.as_view(), name="password_change"),
    path("", include("apps.audits.urls")),
]
