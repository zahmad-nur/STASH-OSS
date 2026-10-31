import time

from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from . import keystore
from .middleware import COOKIE, set_unlock_cookie
from .models import Profile

MIN_PASSPHRASE = 12


def setup(request):
    if keystore.is_setup():
        return redirect("/unlock")
    error = None
    if request.method == "POST":
        p1 = request.POST.get("passphrase", "")
        p2 = request.POST.get("confirm", "")
        if len(p1) < MIN_PASSPHRASE:
            error = f"Use at least {MIN_PASSPHRASE} characters. A few random words works well."
        elif p1 != p2:
            error = "The two passphrases don't match."
        else:
            recovery, token = keystore.setup(p1)
            greeting = request.POST.get("greeting", "").strip()[:60]
            Profile.save_data({
                "name": request.POST.get("name", "").strip()[:60],
                "greeting": greeting,
                # no greeting typed -> pick one from the country on your first I-20
                "greeting_mode": "custom" if greeting else "auto",
            })
            response = render(request, "vault/recovery_key.html", {"recovery": recovery})
            return set_unlock_cookie(response, token)
    return render(request, "vault/setup.html", {"error": error, "min": MIN_PASSPHRASE})


def unlock(request):
    if not keystore.is_setup():
        return redirect("/setup")
    error = None
    if request.method == "POST":
        token = keystore.unlock(request.POST.get("passphrase", ""))
        if token:
            return set_unlock_cookie(redirect("/"), token)
        time.sleep(1)  # slows repeated guessing on top of Argon2id
        error = "That passphrase didn't unlock the vault."
    return render(request, "vault/unlock.html", {"error": error})


def recover(request):
    if not keystore.is_setup():
        return redirect("/setup")
    error = None
    if request.method == "POST":
        new = request.POST.get("passphrase", "")
        if len(new) < MIN_PASSPHRASE:
            error = f"Use at least {MIN_PASSPHRASE} characters for the new passphrase."
        elif new != request.POST.get("confirm", ""):
            error = "The two passphrases don't match."
        else:
            token = keystore.recover(request.POST.get("recovery", ""), new)
            if token:
                return set_unlock_cookie(redirect("/"), token)
            time.sleep(1)
            error = "That recovery key didn't match."
    return render(request, "vault/recover.html", {"error": error, "min": MIN_PASSPHRASE})


@require_POST
def lock(request):
    keystore.lock()
    response = redirect("/unlock")
    response.delete_cookie(COOKIE)
    return response
