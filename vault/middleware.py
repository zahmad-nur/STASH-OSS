from django.http import HttpResponseForbidden
from django.shortcuts import redirect

from . import keystore

COOKIE = "stash_unlock"
OPEN_PREFIXES = ("/setup", "/unlock", "/recover", "/static/")


class LocalOnlyMiddleware:
    """Refuse any request that doesn't come from this computer, even if the server
    was accidentally started on 0.0.0.0."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.META.get("REMOTE_ADDR") not in ("127.0.0.1", "::1"):
            return HttpResponseForbidden("STASH only accepts connections from this computer.")
        return self.get_response(request)


class SecurityHeadersMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        response.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data: blob:; frame-src 'self'; object-src 'self'; "
            "frame-ancestors 'self'; form-action 'self'; base-uri 'none'; connect-src 'self'",
        )
        # Nothing STASH shows should be kept in the browser's disk cache.
        if not request.path.startswith("/static/"):
            response["Cache-Control"] = "no-store"
        response.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        return response


class LockMiddleware:
    """Every page except setup/unlock needs the vault unlocked in this browser."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path.startswith(OPEN_PREFIXES):
            return self.get_response(request)
        if not keystore.is_setup():
            return redirect("/setup")
        if not keystore.touch(request.COOKIES.get(COOKIE)):
            response = redirect("/unlock")
            response.delete_cookie(COOKIE)
            return response
        return self.get_response(request)


def set_unlock_cookie(response, token: str):
    response.set_cookie(COOKIE, token, httponly=True, samesite="Strict", secure=False, path="/")
    return response
