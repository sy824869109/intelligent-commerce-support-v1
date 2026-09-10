"""Fixed reviewed scrypt profile; no custom cryptographic construction."""

import hashlib
import hmac
import secrets


def validate_password(password: str):
    if (
        not isinstance(password, str)
        or not 15 <= len(password) <= 128
        or len(password.encode("utf-8")) > 512
    ):
        raise ValueError("Password must be 15..128 characters and at most 512 UTF-8 bytes")
    if (
        password.lower() in {"passwordpassword", "123456789012345", "password123456789"}
        or len(set(password)) < 5
    ):
        raise ValueError("Password is too predictable")


def derive(password, salt):
    return hashlib.scrypt(
        password.encode("utf-8"), salt=salt, n=131072, r=8, p=1, maxmem=268435456, dklen=32
    )


def hash_password(password: str):
    validate_password(password)
    salt = secrets.token_bytes(16)
    return "scrypt-v1$" + salt.hex() + "$" + derive(password, salt).hex()


def verify_password(password: str, encoded: str):
    try:
        validate_password(password)
        version, salt, expected = encoded.split("$")
        if version != "scrypt-v1" or len(salt) != 32 or len(expected) != 64:
            return False
        return hmac.compare_digest(derive(password, bytes.fromhex(salt)), bytes.fromhex(expected))
    except (ValueError, TypeError):
        return False
