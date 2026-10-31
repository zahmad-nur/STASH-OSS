"""The vault's keys.

One random data key (DEK) encrypts everything. It is never stored in plain form:
- your passphrase, through Argon2id, makes a key that wraps the DEK;
- a one-time recovery key wraps the same DEK, so a forgotten passphrase is recoverable.

Unlocking puts the DEK in this process's memory only. Locking, restarting the app,
or 15 minutes of inactivity clears it.
"""
import base64
import json
import os
import secrets
import threading
import time
from pathlib import Path

from cryptography.exceptions import InvalidTag
from django.conf import settings

from . import crypto

DEK_AAD = b"stash-dek-v1"
_state = {"dek": None, "token": None, "last": 0.0}
_guard = threading.Lock()


class Locked(Exception):
    pass


def _keyfile() -> Path:
    return Path(settings.DATA_DIR) / "keys.json"


def is_setup() -> bool:
    return _keyfile().exists()


def _write_keyfile(data: dict) -> None:
    path = _keyfile()
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2))
    try:
        os.chmod(tmp, 0o600)
    except OSError:
        pass
    os.replace(tmp, path)


def _read_keyfile() -> dict:
    return json.loads(_keyfile().read_text())


def _wrap(secret: bytes, dek: bytes) -> dict:
    salt = os.urandom(16)
    kek = crypto.derive_key(secret, salt)
    return {"salt": crypto.b64(salt), "wrapped": crypto.b64(crypto.seal(kek, dek, DEK_AAD))}


def _unwrap(secret: bytes, entry: dict, params: dict) -> bytes | None:
    kek = crypto.derive_key(secret, crypto.unb64(entry["salt"]), params)
    try:
        return crypto.unseal(kek, crypto.unb64(entry["wrapped"]), DEK_AAD)
    except InvalidTag:
        return None


def _format_recovery(raw: bytes) -> str:
    text = base64.b32encode(raw).decode().rstrip("=")
    return "-".join(text[i:i + 4] for i in range(0, len(text), 4))


def _parse_recovery(text: str) -> bytes | None:
    cleaned = "".join(ch for ch in text.upper() if ch.isalnum())
    try:
        return base64.b32decode(cleaned + "=" * (-len(cleaned) % 8))
    except (ValueError, base64.binascii.Error):
        return None


def setup(passphrase: str) -> tuple[str, str]:
    """First run. Returns (recovery_key_to_show_once, session_token)."""
    if is_setup():
        raise RuntimeError("The vault already exists.")
    dek = os.urandom(32)
    recovery_raw = os.urandom(20)
    _write_keyfile({
        "version": 1,
        "kdf": "argon2id",
        "params": crypto.KDF_PARAMS,
        "passphrase": _wrap(passphrase.encode(), dek),
        "recovery": _wrap(recovery_raw, dek),
    })
    return _format_recovery(recovery_raw), _activate(dek)


def unlock(passphrase: str) -> str | None:
    data = _read_keyfile()
    dek = _unwrap(passphrase.encode(), data["passphrase"], data["params"])
    return _activate(dek) if dek else None


def recover(recovery_key: str, new_passphrase: str) -> str | None:
    """Unlock with the recovery key and set a new passphrase."""
    raw = _parse_recovery(recovery_key)
    if raw is None:
        return None
    data = _read_keyfile()
    dek = _unwrap(raw, data["recovery"], data["params"])
    if not dek:
        return None
    data["passphrase"] = _wrap(new_passphrase.encode(), dek)
    _write_keyfile(data)
    return _activate(dek)


def change_passphrase(old: str, new: str) -> bool:
    data = _read_keyfile()
    dek = _unwrap(old.encode(), data["passphrase"], data["params"])
    if not dek:
        return False
    data["passphrase"] = _wrap(new.encode(), dek)
    _write_keyfile(data)
    return True


def _activate(dek: bytes) -> str:
    with _guard:
        token = secrets.token_urlsafe(32)
        _state.update(dek=dek, token=token, last=time.monotonic())
        return token


def lock() -> None:
    with _guard:
        _state.update(dek=None, token=None, last=0.0)


def touch(token: str | None) -> bool:
    """True if this browser holds the current unlock token and the vault hasn't idled out."""
    with _guard:
        if not _state["dek"] or not token or not _state["token"]:
            return False
        if not secrets.compare_digest(token, _state["token"]):
            return False
        if time.monotonic() - _state["last"] > settings.STASH_IDLE_SECONDS:
            _state.update(dek=None, token=None, last=0.0)
            return False
        _state["last"] = time.monotonic()
        return True


def dek() -> bytes:
    with _guard:
        if not _state["dek"]:
            raise Locked()
        return _state["dek"]
