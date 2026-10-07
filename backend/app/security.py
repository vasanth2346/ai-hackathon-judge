from cryptography.fernet import Fernet, InvalidToken

from app.config import get_settings


def encrypt_secret(value: str) -> str:
    key = get_settings().judge_encryption_key
    if not key:
        raise ValueError("Set JUDGE_ENCRYPTION_KEY before storing demo credentials")
    return Fernet(key.encode()).encrypt(value.encode()).decode()


def decrypt_secret(value: str) -> str:
    key = get_settings().judge_encryption_key
    if not key:
        raise ValueError("JUDGE_ENCRYPTION_KEY is not configured")
    try:
        return Fernet(key.encode()).decrypt(value.encode()).decode()
    except InvalidToken as exc:
        raise ValueError("Could not decrypt stored demo credentials") from exc

