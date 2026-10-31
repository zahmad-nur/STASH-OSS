from django.conf import settings
from django.urls import include, path, re_path
from django.views.static import serve

urlpatterns = [
    path("", include("dashboard.urls")),
    path("", include("vault.urls")),
    path("documents/", include("documents.urls")),
    # Local app: serve our own CSS/JS/logo directly. No CDNs, no outside requests.
    re_path(r"^static/(?P<path>.*)$", serve, {"document_root": settings.BASE_DIR / "static"}),
]
