import datetime
import os
from pathlib import Path

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography import x509
from cryptography.x509.oid import NameOID
from django.conf import settings


def genereaza_credentiale_utilizator(utilizator):
    """
    Generează o pereche cheie privată + certificat X.509 self-signed
    pentru un utilizator și le salvează pe modelul său.

    Cheia privată e criptată cu Fernet înainte de salvare în DB —
    același mecanism folosit pentru CNP-uri în Etapa 7.
    Certificatul e stocat în clar (e public prin definiție).

    Apelată la prima semnare dacă utilizatorul nu are credențiale.
    """
    # Generează cheie privată RSA 2048 biți
    cheie_privata = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
    )

    # Construiește certificatul X.509 self-signed
    nume = utilizator.get_full_name() or utilizator.username
    subiect = x509.Name([
        x509.NameAttribute(NameOID.COMMON_NAME, nume),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "CMS Demo Parchet"),
        x509.NameAttribute(NameOID.COUNTRY_NAME, "RO"),
    ])

    certificat = (
        x509.CertificateBuilder()
        .subject_name(subiect)
        .issuer_name(subiect)
        .public_key(cheie_privata.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.datetime.utcnow())
        .not_valid_after(
            datetime.datetime.utcnow() + datetime.timedelta(days=365 * 2)
        )
        .add_extension(
            x509.BasicConstraints(ca=False, path_length=None),
            critical=True
        )
        .sign(cheie_privata, hashes.SHA256())
    )

    # Serializează cheia privată în format PEM
    cheie_privata_pem = cheie_privata.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption()
    )

    # Criptează cheia privată cu Fernet înainte de salvare
    f = Fernet(settings.FERNET_KEY.encode()
               if isinstance(settings.FERNET_KEY, str)
               else settings.FERNET_KEY)
    cheie_privata_criptata = f.encrypt(cheie_privata_pem)

    # Serializează certificatul în format PEM (text)
    certificat_pem = certificat.public_bytes(
        serialization.Encoding.PEM
    ).decode('utf-8')

    # Salvează pe modelul utilizatorului
    utilizator.cheie_privata_criptata = cheie_privata_criptata
    utilizator.certificat_pem = certificat_pem
    utilizator.save()