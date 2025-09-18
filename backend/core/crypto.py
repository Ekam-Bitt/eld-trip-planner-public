import os

from cryptography.fernet import Fernet, InvalidToken


def get_fernet() -> Fernet:
    key = os.environ.get("MAPBOX_ENC_KEY")
    if not key:
        raise RuntimeError(
            "MAPBOX_ENC_KEY is not set. Provide a base64-encoded 32-byte "
            "Fernet key via environment."
        )
    return Fernet(key)


def encrypt_value(plaintext: str) -> str:
    fernet = get_fernet()
    return fernet.encrypt(plaintext.encode("utf-8")).decode("utf-8")


def decrypt_value(ciphertext: str) -> str:
    fernet = get_fernet()
    try:
        return fernet.decrypt(ciphertext.encode("utf-8")).decode("utf-8")
    except InvalidToken:
        raise RuntimeError("Failed to decrypt value. Check MAPBOX_ENC_KEY consistency.")
