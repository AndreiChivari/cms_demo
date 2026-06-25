from django.db import models
from django.conf import settings
from django.utils import timezone
from .utils import curata_diacritice
from django.contrib.auth.models import AbstractUser
from simple_history.models import HistoricalRecords
from .fields import EncryptedField
from .crypto import calculeaza_hmac

class CustomUser(AbstractUser):
    """
    Modelul custom de utilizator al aplicației.
    Moștenește tot de la AbstractUser și adaugă câmpuri specifice parchetului.
    """
    class Functie(models.TextChoices):
        PROCUROR = 'PROCUROR', 'Procuror'
        OFITER = 'OFITER', 'Ofițer de urmărire penală'
        GREFIER = 'GREFIER', 'Grefier'
        ADMIN = 'ADMIN', 'Administrator sistem'

    functie = models.CharField(
        max_length=20,
        choices=Functie.choices,
        blank=True, null=True
    )
    parafa = models.CharField(
        max_length=20,
        blank=True, null=True,
        verbose_name="Parafă",
        help_text="Codul de identificare al procurorului/ofițerului"
    )
    # Dacă utilizatorul și-a configurat 2FA
    otp_configurat = models.BooleanField(
        default=False,
        verbose_name="2FA configurat"
    )

    class Meta:
        verbose_name = "Utilizator"
        verbose_name_plural = "Utilizatori"

    def __str__(self):
        return f"{self.get_full_name()} ({self.get_functie_display()})"


class Dosar(models.Model):
    """
    Entitatea centrală a aplicației.
    Toate celelalte entități gravitează în jurul dosarului.
    """
    class StareDosar(models.TextChoices):
        ACTIV = 'ACTIV', 'Activ'
        SUSPENDAT = 'SUSPENDAT', 'Suspendat'
        INCHIS = 'INCHIS', 'Închis'
        CLASAT = 'CLASAT', 'Clasat'

    numar_unic = models.CharField(
        max_length=50,
        unique=True,
        verbose_name="Număr unic dosar"
    )
    data_deschiderii = models.DateField(default=timezone.now)
    stare = models.CharField(
        max_length=20,
        choices=StareDosar.choices,
        default=StareDosar.ACTIV
    )
    infractiune_cercetata = models.CharField(
        max_length=200,
        verbose_name="Infracțiunea cercetată"
    )
    descriere = models.TextField(blank=True, null=True)

    # Echipa dosarului
    procuror_caz = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='dosare_procuror'
    )
    ofiter_caz = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='dosare_ofiter'
    )

    # Câmp shadow pentru căutare fără diacritice
    infractiune_cercetata_ascii = models.CharField(
        max_length=200, blank=True, editable=False
    )

    history = HistoricalRecords()  # ← adaugă la sfârșitul câmpurilor, înainte de Meta

    class Meta:
        verbose_name = "Dosar"
        verbose_name_plural = "Dosare"
        ordering = ['-data_deschiderii']

    def __str__(self):
        return f"Dosar {self.numar_unic} — {self.infractiune_cercetata}"

    def save(self, *args, **kwargs):
        self.infractiune_cercetata_ascii = curata_diacritice(self.infractiune_cercetata)
        super().save(*args, **kwargs)


class ParteImplicata(models.Model):
    """
    O persoană fizică sau juridică implicată într-un dosar.
    Câmpurile sensibile (CNP) vor fi criptate în Etapa 7.
    """
    class Calitate(models.TextChoices):
        SUSPECT = 'SUSPECT', 'Suspect'
        INCULPAT = 'INCULPAT', 'Inculpat'
        PARTE_VATAMATA = 'PARTE_VATAMATA', 'Parte Vătămată'
        MARTOR = 'MARTOR', 'Martor'
        EXPERT = 'EXPERT', 'Expert'

    dosar = models.ForeignKey(
        Dosar,
        on_delete=models.CASCADE,
        related_name='parti_implicate'
    )
    nume_complet = models.CharField(max_length=200)

    cnp = EncryptedField(
        blank=True, null=True,
        verbose_name="CNP"
    )
    # Hash HMAC pentru căutare — nu poate fi inversat fără cheia secretă
    cnp_hash = models.CharField(
        max_length=64,
        blank=True, null=True,
        editable=False,  # invizibil în formulare și admin
        verbose_name="CNP Hash (index)"
    )
    calitate = models.CharField(
        max_length=30,
        choices=Calitate.choices,
        default=Calitate.SUSPECT
    )
    adresa = models.CharField(max_length=300, blank=True, null=True)
    email = models.EmailField(blank=True, null=True)

    # Câmpuri shadow
    nume_complet_ascii = models.CharField(max_length=200, blank=True, editable=False)
    adresa_ascii = models.CharField(max_length=300, blank=True, editable=False)

    history = HistoricalRecords()  # ← adaugă la sfârșitul câmpurilor, înainte de Meta

    class Meta:
        verbose_name = "Parte Implicată"
        verbose_name_plural = "Părți Implicate"

    def __str__(self):
        return f"{self.nume_complet} ({self.get_calitate_display()}) — {self.dosar.numar_unic}"

    def save(self, *args, **kwargs):
        # Calculăm hash-ul ÎNAINTE de criptare — lucrăm cu CNP-ul în clar
        if self.cnp:
            self.cnp_hash = calculeaza_hmac(self.cnp)
        self.nume_complet_ascii = curata_diacritice(self.nume_complet)
        self.adresa_ascii = curata_diacritice(self.adresa)
        super().save(*args, **kwargs)


class Infractiune(models.Model):
    """
    O infracțiune concretă cercetată în cadrul dosarului.
    Conține adresa comiterii — folosită pentru harta infracționalității (Etapa 9).
    """
    dosar = models.ForeignKey(
        Dosar,
        on_delete=models.CASCADE,
        related_name='infractiuni'
    )
    incadrare_juridica = models.CharField(
        max_length=200,
        verbose_name="Încadrare juridică",
        help_text="Ex: Art. 208 Cod Penal — Furt"
    )
    data_comiterii = models.DateField(null=True, blank=True)
    adresa_comiterii = models.CharField(max_length=300, blank=True, null=True)

    # Coordonate pentru Leaflet.js — populate de geocoder (Etapa 9)
    latitudine = models.FloatField(null=True, blank=True)
    longitudine = models.FloatField(null=True, blank=True)

    # Câmpuri shadow
    incadrare_juridica_ascii = models.CharField(max_length=200, blank=True, editable=False)
    adresa_comiterii_ascii = models.CharField(max_length=300, blank=True, editable=False)

    history = HistoricalRecords()  # ← adaugă la sfârșitul câmpurilor, înainte de Meta

    class Meta:
        verbose_name = "Infracțiune"
        verbose_name_plural = "Infracțiuni"

    def __str__(self):
        return f"{self.incadrare_juridica} — {self.dosar.numar_unic}"

    def save(self, *args, **kwargs):
        self.incadrare_juridica_ascii = curata_diacritice(self.incadrare_juridica)
        self.adresa_comiterii_ascii = curata_diacritice(self.adresa_comiterii)
        super().save(*args, **kwargs)


class StadiuCercetare(models.Model):
    """
    Istoricul stadiilor unui dosar — formează o linie de timp.
    Un dosar trece prin mai multe stadii pe parcursul cercetării.
    """
    class TipStadiu(models.TextChoices):
        INCEPERE = 'INCEPERE', 'Începerea urmăririi penale'
        PUNERE_SUB_INVINUIRE = 'PUNERE_SUB_INVINUIRE', 'Punere sub învinuire'
        TRIMITERE_JUDECATA = 'TRIMITERE_JUDECATA', 'Trimitere în judecată'
        CLASARE = 'CLASARE', 'Clasare'
        SUSPENDARE = 'SUSPENDARE', 'Suspendare'

    dosar = models.ForeignKey(
        Dosar,
        on_delete=models.CASCADE,
        related_name='stadii'
    )
    tip = models.CharField(max_length=50, choices=TipStadiu.choices)
    data = models.DateField(default=timezone.now)
    observatii = models.TextField(blank=True, null=True)
    inregistrat_de = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True
    )
    history = HistoricalRecords()  # ← adaugă la sfârșitul câmpurilor, înainte de Meta

    class Meta:
        verbose_name = "Stadiu Cercetare"
        verbose_name_plural = "Stadii Cercetare"
        ordering = ['-data']

    def __str__(self):
        return f"{self.get_tip_display()} — {self.dosar.numar_unic} ({self.data})"


class MasuraPreventiva(models.Model):
    """
    O măsură preventivă aplicată unei persoane din dosar.
    Are dată de start și expirare — logica de expirare va genera notificări (Etapa 11).
    """
    class TipMasura(models.TextChoices):
        RETINERE = 'RETINERE', 'Reținere'
        AREST_PREVENTIV = 'AREST_PREVENTIV', 'Arest preventiv'
        CONTROL_JUDICIAR = 'CONTROL_JUDICIAR', 'Control judiciar'
        INTERDICTIE = 'INTERDICTIE', 'Interdicție'

    parte = models.ForeignKey(
        ParteImplicata,
        on_delete=models.CASCADE,
        related_name='masuri_preventive'
    )
    tip = models.CharField(max_length=30, choices=TipMasura.choices)
    data_start = models.DateField(default=timezone.now)
    data_expirare = models.DateField(null=True, blank=True)
    activa = models.BooleanField(default=True)
    dispusa_de = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True
    )
    history = HistoricalRecords()  # ← adaugă la sfârșitul câmpurilor, înainte de Meta

    class Meta:
        verbose_name = "Măsură Preventivă"
        verbose_name_plural = "Măsuri Preventive"
        ordering = ['-data_start']

    def __str__(self):
        return f"{self.get_tip_display()} — {self.parte.nume_complet}"