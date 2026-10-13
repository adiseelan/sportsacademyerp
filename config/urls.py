from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from django.views.generic import RedirectView

urlpatterns = [
    path("admin/", admin.site.urls),
    path("auth/", include("apps.accounts.urls")),
    path("app/", include("apps.portal.urls")),
    path("", RedirectView.as_view(pattern_name="portal:home", permanent=False)),
]

# Uploaded media (branch photos). Served by Django only in DEBUG; in production
# map /media/ to MEDIA_ROOT on the web server (see DEPLOY_PYTHONANYWHERE.md).
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

# Friendly error handlers
handler403 = "apps.portal.views.common.error_403"
handler404 = "apps.portal.views.common.error_404"
handler500 = "apps.portal.views.common.error_500"
