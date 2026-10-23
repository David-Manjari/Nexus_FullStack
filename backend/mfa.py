"""TOTP, encrypted secret storage, and recovery-code helpers."""

import base64
import hashlib
import hmac
import secrets
import struct
import time

from cryptography.fernet import Fernet
from flask import current_app


def generate_totp_secret():
    return base64.b32encode(secrets.token_bytes(20)).decode("ascii").rstrip("=")


def _fernet():
    key_material = current_app.config["SECRET_KEY"]
    if isinstance(key_material, str):
        key_material = key_material.encode("utf-8")
    derived_key = hmac.new(
        key_material, b"nexus-totp-secret-encryption-v1", hashlib.sha256
    ).digest()
    return Fernet(base64.urlsafe_b64encode(derived_key))


def encrypt_totp_secret(secret):
    return _fernet().encrypt(secret.encode("ascii")).decode("ascii")


def decrypt_totp_secret(encrypted_secret):
    return _fernet().decrypt(encrypted_secret.encode("ascii")).decode("ascii")


def _totp(secret, counter):
    key = base64.b32decode(secret + "=" * (-len(secret) % 8), casefold=True)
    digest = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    value = struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF
    return f"{value % 1_000_000:06d}"


def verify_totp(secret, code, *, now=None):
    if not isinstance(code, str) or len(code) != 6 or not code.isdigit():
        return False
    counter = int((time.time() if now is None else now) // 30)
    return any(
        hmac.compare_digest(_totp(secret, counter + offset), code)
        for offset in (-1, 0, 1)
    )


def generate_recovery_codes(count=10):
    codes = [secrets.token_hex(8).upper() for _ in range(count)]
    hashes = [hashlib.sha256(code.encode("ascii")).hexdigest() for code in codes]
    return codes, hashes


def consume_recovery_code(code, hashes):
    if not isinstance(code, str):
        return None
    normalized = code.replace("-", "").replace(" ", "").upper()
    if len(normalized) != 16 or any(char not in "0123456789ABCDEF" for char in normalized):
        return None
    submitted_hash = hashlib.sha256(normalized.encode("ascii")).hexdigest()
    for index, stored_hash in enumerate(hashes):
        if hmac.compare_digest(submitted_hash, stored_hash):
            return index
    return None
