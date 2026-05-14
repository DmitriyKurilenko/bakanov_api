from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path

from apps.integrations.views import (
    bitrix24_app,
    bitrix24_contract_form,
    bitrix24_contract_generate,
    bitrix24_install,
)
from config.api import api

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", api.urls),
    path("bitrix24/install/", bitrix24_install, name="bitrix24-install"),
    path("bitrix24/app/", bitrix24_app, name="bitrix24-app"),
    path("bitrix24/contract/", bitrix24_contract_form, name="bitrix24-contract-form"),
    path("bitrix24/contract/generate/", bitrix24_contract_generate, name="bitrix24-contract-generate"),
    path("", include("apps.dashboard.urls")),
    path("login/", auth_views.LoginView.as_view(template_name="dashboard/login.html"), name="login"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("accounts/login/", auth_views.LoginView.as_view(template_name="dashboard/login.html"), name="accounts-login"),
    path("accounts/logout/", auth_views.LogoutView.as_view(), name="accounts-logout"),
]

urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
