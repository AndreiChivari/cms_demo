from django.db import models
from .crypto import cripteaza, decripteaza


class EncryptedField(models.TextField):
    """
    Câmp Django care criptează automat valoarea înainte de salvare
    și o decriptează automat după citire din baza de date.

    Din perspectiva codului Python, câmpul se comportă ca un TextField normal.
    Din perspectiva bazei de date, stochează doar text criptat.

    Moștenește din TextField pentru că textul criptat (base64) poate fi
    mai lung decât inputul original și nu are lungime fixă.
    """

    def get_prep_value(self, value):
        """
        Apelat de Django înainte de a scrie în baza de date.
        Criptează valoarea.
        """
        value = super().get_prep_value(value)
        return cripteaza(value)

    def from_db_value(self, value, expression, connection):
        """
        Apelat de Django după fiecare citire din baza de date.
        Decriptează valoarea.
        """
        return decripteaza(value)

    def to_python(self, value):
        """
        Apelat la deserializare și validare în formulare.
        Încearcă decriptarea dacă valoarea pare criptată.
        """
        if value is None:
            return value
        # Dacă valoarea a trecut deja prin from_db_value e deja decriptată
        # Dacă vine din formular e în clar — o returnăm ca atare
        try:
            decriptat = decripteaza(value)
            return decriptat if decriptat is not None else value
        except Exception:
            return value