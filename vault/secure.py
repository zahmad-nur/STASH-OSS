"""Encryption helpers the rest of the app uses. Each purpose gets its own sub-key."""
import json
import os
import secrets
from pathlib import Path

from django.conf import settings

from . import crypto, keystore


def _key(purpose: bytes) -> bytes:
    return crypto.subkey(keystore.dek(), purpose)


def encrypt_json(obj, aad: bytes) -> bytes:
    return crypto.seal(_key(b"stash-fields-v1"), json.dumps(obj).encode(), aad)


def decrypt_json(blob, aad: bytes):
    if not blob:
        return {}
    return json.loads(crypto.unseal(_key(b"stash-fields-v1"), bytes(blob), aad))


def fingerprint(data: bytes) -> str:
    return crypto.keyed_hash(_key(b"stash-dedupe-v1"), data)


# ---- encrypted file store -------------------------------------------------

def _files_dir() -> Path:
    return Path(settings.DATA_DIR) / "files"


def put_file(data: bytes, aad: bytes) -> str:
    """Encrypts and writes a file under a random name. Returns the name."""
    name = secrets.token_hex(16)
    path = _files_dir() / f"{name}.bin"
    path.write_bytes(crypto.seal(_key(b"stash-files-v1"), data, aad))
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    return name


def get_file(name: str, aad: bytes) -> bytes:
    if not name.isalnum():
        raise ValueError("bad file name")
    blob = (_files_dir() / f"{name}.bin").read_bytes()
    return crypto.unseal(_key(b"stash-files-v1"), blob, aad)


def delete_file(name: str) -> None:
    if name.isalnum():
        (_files_dir() / f"{name}.bin").unlink(missing_ok=True)
