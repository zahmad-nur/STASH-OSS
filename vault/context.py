from pathlib import Path

from django.conf import settings

from . import greetings, keystore
from .models import Profile


def _short(path) -> str:
    """Show the data folder with ~ for the home folder."""
    p, home = Path(path), Path.home()
    try:
        return "~/" + str(p.relative_to(home))
    except ValueError:
        return str(p)


def shell(request):
    """Data folder for the footer; greeting for the header only when the vault is unlocked."""
    ctx = {"data_dir": _short(settings.DATA_DIR), "demo": getattr(settings, "STASH_DEMO", False)}
    try:
        keystore.dek()
    except keystore.Locked:
        return ctx
    profile = Profile.load()
    ctx.update(profile_name=profile.get("name", ""), greeting=greetings.resolve(profile))
    return ctx
