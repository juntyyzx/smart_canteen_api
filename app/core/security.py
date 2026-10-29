"""Пароли (scrypt) и токены доступа. Пароли и токены в открытом виде не хранятся."""
import base64
import hashlib
import hmac
import secrets

_N, _R, _P = 2 ** 14, 8, 1


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=_N, r=_R, p=_P, dklen=32)
    return "scrypt${}${}".format(base64.b64encode(salt).decode(), base64.b64encode(digest).decode())


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, salt_b64, digest_b64 = stored.split("$")
        if scheme != "scrypt":
            return False
        salt = base64.b64decode(salt_b64)
        expected = base64.b64decode(digest_b64)
        actual = hashlib.scrypt(password.encode(), salt=salt, n=_N, r=_R, p=_P, dklen=len(expected))
        return hmac.compare_digest(actual, expected)
    except Exception:
        return False


_DUMMY_HASH = hash_password("dummy-password-for-timing")


def burn_password_check(password: str) -> None:
    """Выравнивает время ответа, когда пользователь не найден."""
    verify_password(password, _DUMMY_HASH)


def new_token() -> str:
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()
