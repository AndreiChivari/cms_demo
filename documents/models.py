from django.db import models
from django.conf import settings
from django.utils import timezone
from django.core.exceptions import ValidationError
from cases.models import Dosar
from cases.utils import curata_diacritice
import os
import uuid


def cale_upload_document(instance, filename):
    """
    Generează cale unică: documente/dosar_<ID>/<UUID>.<ext>
    UUID previne suprascrierea fișierelor cu același nume original.
    """
    ext = filename.split('.')[-1].lower()
    nume_nou = f"{uuid.uuid4().hex}.{ext}"
    folder_dosar = f"dosar_{instance.dosar.id}" if instance.dosar else "nesortate"
    return os.path.join('documente', folder_dosar, nume_nou)


def valideaza_extensie_document(value):
    extensii_permise = ['.pdf', '.doc', '.docx', '.jpg', '.jpeg', '.png']
    ext = os.path.splitext(value.name)[1].lower()
    if ext not in extensii_permise:
        raise ValidationError(
            f"Format neacceptat: {ext}. Permise: PDF, DOC, DOCX, JPG, PNG."
        )


def valideaza_dimensiune_document(value):
    limita_mb = 10
    if value.size > limita_mb * 1024 * 1024:
        raise ValidationError(
            f"Fișierul depășește limita de {limita_mb}MB."
        )


class ActUrmarire(models.Model):
    class TipDocument(models.TextChoices):
        ORDONANTA = 'ORDONANTA', 'Ordonanță'
        REFERAT = 'REFERAT', 'Referat'
        DECLARATIE = 'DECLARATIE', 'Declarație'
        PROCES_VERBAL = 'PROCES_VERBAL', 'Proces-Verbal'
        ALTUL = 'ALTUL', 'Alt tip de act'

    titlu = models.CharField(max_length=255, blank=True, null=True)
    tip = models.CharField(
        max_length=50,
        choices=TipDocument.choices,
        default=TipDocument.ORDONANTA
    )
    dosar = models.ForeignKey(
        Dosar,
        on_delete=models.CASCADE,
        related_name='documente'
    )
    autor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True
    )
    fisier = models.FileField(
        upload_to=cale_upload_document,
        validators=[valideaza_extensie_document, valideaza_dimensiune_document]
    )
    data_documentului = models.DateField(default=timezone.now)
    data_inregistrarii = models.DateField(default=timezone.now)
    data_incarcarii = models.DateTimeField(auto_now_add=True)
    descriere_scurta = models.TextField(blank=True, null=True)

    # Câmpuri shadow
    titlu_ascii = models.CharField(max_length=255, blank=True, editable=False)
    descriere_scurta_ascii = models.TextField(blank=True, editable=False)

    # Semnătură digitală — logica în cases/ (Etapa 10)
    fisier_semnat = models.FileField(
        upload_to='documente/semnate/%Y/%m/',
        null=True, blank=True
    )
    este_semnat = models.BooleanField(default=False)
    semnat_de = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='acte_semnate_de_mine'
    )
    data_semnarii = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "Act de Urmărire Penală"
        verbose_name_plural = "Acte de Urmărire Penală"
        ordering = ['-data_incarcarii']

    def __str__(self):
        return f"{self.get_tip_display()} — {self.titlu} ({self.dosar.numar_unic})"

    def are_drepturi_editare(self, utilizator):
        if self.autor == utilizator:
            return True
        echipa = [self.dosar.ofiter_caz, self.dosar.procuror_caz]
        return utilizator in echipa

    def save(self, *args, **kwargs):
        self.titlu_ascii = curata_diacritice(self.titlu)
        self.descriere_scurta_ascii = curata_diacritice(self.descriere_scurta)
        super().save(*args, **kwargs)


class TrimiterePrinEmail(models.Model):
    document = models.ForeignKey(
        ActUrmarire,
        on_delete=models.CASCADE,
        related_name='trimiteri_email'
    )
    trimis_de = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='emailuri_trimise'
    )
    trimis_la = models.DateTimeField(auto_now_add=True)
    email_destinatar = models.EmailField()
    nume_destinatar = models.CharField(max_length=200)
    subiect = models.CharField(max_length=255)
    mesaj = models.TextField(blank=True)
    reusit = models.BooleanField(default=True)
    varianta_trimisa = models.CharField(
        max_length=10,
        choices=[('original', 'Original'), ('semnat', 'Semnat')],
        default='original'
    )

    class Meta:
        verbose_name = "Trimitere Email Document"
        verbose_name_plural = "Trimiteri Email Documente"
        ordering = ['-trimis_la']

    def __str__(self):
        return f"{self.document.titlu} → {self.email_destinatar}"