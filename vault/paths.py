"""Where STASH keeps your data: always outside the code folder."""
import os
import secrets
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured
from platformdirs import user_data_dir


def _private_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(path, 0o700)
    except OSError:
        pass  # Windows ignores POSIX modes; the folder sits in your user profile.
    return path


def _default_dir() -> str:
    """The standard place for app data on your OS. A folder from an earlier
    version ("STASH Personal") keeps working if it's already there."""
    current = user_data_dir("STASH", "stash")
    older = user_data_dir("STASH Personal", "stash")
    if not Path(current).exists() and Path(older).exists():
        return older
    return current


def data_dir(code_dir: Path) -> Path:
    """Your data folder. Set STASH_DATA_DIR to move it.

    Refuses any location inside the code folder, so your documents can never be
    committed to git by accident.
    """
    raw = os.environ.get("STASH_DATA_DIR") or _default_dir()
    path = Path(raw).expanduser().resolve()
    code = code_dir.resolve()
    if path == code or code in path.parents:
        raise ImproperlyConfigured(
            f"STASH_DATA_DIR ({path}) is inside the code folder. Choose a folder outside {code}."
        )
    _private_dir(path)
    _private_dir(path / "files")
    return path


def secret_key(data: Path) -> str:
    """Django's secret key, generated on first run and stored in the data folder."""
    key_file = data / "secret_key"
    if not key_file.exists():
        key_file.write_text(secrets.token_urlsafe(50))
        try:
            os.chmod(key_file, 0o600)
        except OSError:
            pass
    return key_file.read_text().strip()
