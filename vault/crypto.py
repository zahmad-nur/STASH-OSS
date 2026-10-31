"""Low-level encryption. Everything else in STASH goes through these functions.

- AES-256-GCM for all encryption (confidentiality + tamper detection).
- Argon2id to turn a passphrase into a key (slow on purpose, resists guessing).
- HKDF to derive separate sub-keys for files, fields and duplicate detection.
"""
import base64
import os

from argon2.low_level import Type, hash_secret_raw
from cryptography.hazmat.primitives import hashes, hmac
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

# Argon2id cost: ~64 MiB of memory and a fraction of a second per attempt.
KDF_PARAMS = {"time_cost": 3, "memory_cost": 65536, "parallelism": 4}
NONCE_BYTES = 12


def derive_key(secret: bytes, salt: bytes, params: dict = KDF_PARAMS) -> bytes:
    return hash_secret_raw(
        secret,
        salt,
        time_cost=params["time_cost"],
        memory_cost=params["memory_cost"],
        parallelism=params["parallelism"],
        hash_len=32,
        type=Type.ID,
    )


def seal(key: bytes, plaintext: bytes, aad: bytes = b"") -> bytes:
    """Encrypt. `aad` binds the ciphertext to its owner (a row or file id),
    so an encrypted value can't be swapped onto another record unnoticed."""
    nonce = os.urandom(NONCE_BYTES)
    return nonce + AESGCM(key).encrypt(nonce, plaintext, aad)


def unseal(key: bytes, blob: bytes, aad: bytes = b"") -> bytes:
    """Decrypt. Raises cryptography.exceptions.InvalidTag on a wrong key or tampering."""
    return AESGCM(key).decrypt(blob[:NONCE_BYTES], blob[NONCE_BYTES:], aad)


def subkey(master: bytes, purpose: bytes) -> bytes:
    return HKDF(algorithm=hashes.SHA256(), length=32, salt=None, info=purpose).derive(master)


def keyed_hash(key: bytes, data: bytes) -> str:
    """A fingerprint only this vault can compute. Used to spot duplicate uploads
    without storing a plain hash anyone could match against a known file."""
    h = hmac.HMAC(key, hashes.SHA256())
    h.update(data)
    return h.finalize().hex()


def b64(data: bytes) -> str:
    return base64.b64encode(data).decode()


def unb64(text: str) -> bytes:
    return base64.b64decode(text)
