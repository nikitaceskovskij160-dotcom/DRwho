from cryptography.fernet import Fernet, MultiFernet


class Crypto:
    """Шифрование полей с медданными. ENCRYPTION_KEY может содержать несколько ключей
    через запятую: первым шифруется, остальными только расшифровывается (ротация)."""

    def __init__(self, keys: str) -> None:
        fernets = [Fernet(k.strip().encode()) for k in keys.split(",") if k.strip()]
        if not fernets:
            raise ValueError("ENCRYPTION_KEY не задан")
        self._fernet = MultiFernet(fernets)

    def encrypt(self, value: str) -> str:
        return self._fernet.encrypt(value.encode()).decode()

    def decrypt(self, token: str) -> str:
        return self._fernet.decrypt(token.encode()).decode()


_crypto: Crypto | None = None


def init_crypto(keys: str) -> None:
    global _crypto
    _crypto = Crypto(keys)


def get_crypto() -> Crypto:
    if _crypto is None:
        raise RuntimeError("Шифрование не инициализировано: вызовите init_crypto()")
    return _crypto
