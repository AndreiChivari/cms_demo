import hmac
import hashlib
import base64
from cryptography.fernet import Fernet
from django.conf import settings


def get_fernet():
    """
    Returnează o instanță Fernet cu cheia din settings.
    Ridicăm o eroare clară dacă cheia nu e configurată —
    mai bine eșuăm explicit decât să stocăm date necriptate silențios.
    """
    if not settings.FERNET_KEY:
        raise ValueError(
            "FERNET_KEY nu este configurată în settings. "
            "Adaugă cheia în fișierul .env"
        )
    return Fernet(settings.FERNET_KEY.encode() if isinstance(settings.FERNET_KEY, str) else settings.FERNET_KEY)


def cripteaza(text):
    """
    Criptează un string și returnează rezultatul ca string base64.
    Returnează None dacă inputul e None sau gol.
    """
    if not text:
        return None
    f = get_fernet()
    # encode() convertește string → bytes (Fernet lucrează cu bytes)
    # decrypt() returnează bytes → decode() convertește înapoi la string
    return f.encrypt(text.encode('utf-8')).decode('utf-8')


def decripteaza(text_criptat):
    """
    Decriptează un string criptat cu Fernet.
    Returnează None dacă inputul e None sau dacă decriptarea eșuează.
    """
    if not text_criptat:
        return None
    try:
        f = get_fernet()
        return f.decrypt(text_criptat.encode('utf-8')).decode('utf-8')
    except Exception:
        # Dacă token-ul e corupt sau cheia e greșită — returnăm None
        # în loc să propagăm excepția și să crăpăm aplicația
        return None


def calculeaza_hmac(text):
    """
    Calculează HMAC-SHA256 al unui text folosind HMAC_KEY din settings.
    Returnează hash-ul ca string hex — determinist, același input → același output.
    Folosit pentru blind indexing: căutare după CNP fără să stocăm CNP-ul în clar.
    """
    if not text:
        return None
    if not settings.HMAC_KEY:
        raise ValueError("HMAC_KEY nu este configurată în settings.")
    
    return hmac.new(
        settings.HMAC_KEY.encode('utf-8'),  # cheia secretă
        text.encode('utf-8'),               # mesajul (CNP-ul)
        hashlib.sha256                       # funcția hash
    ).hexdigest()  # returnează hash-ul ca string hex de 64 caractere