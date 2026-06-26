from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django_otp.plugins.otp_totp.models import TOTPDevice
from django_otp import devices_for_user
import qrcode
import qrcode.image.svg
from io import BytesIO
import base64
from django.core.paginator import Paginator
from django.db.models import Q
from cases.models import Dosar, ParteImplicata, Infractiune
from cases.utils import curata_diacritice
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from cases.ocr import proceseaza_act_identitate
import json
from pathlib import Path
from django.utils import timezone
import os

from cms_demo import settings


def view_autentificare(request):
    """
    Pasul 1 din autentificare: username + parolă.
    Dacă credențialele sunt corecte, redirecționează la verificare OTP
    (middleware-ul Force2FA va intercepta și va cere codul).
    """
    eroare = None

    if request.method == 'POST':
        username = request.POST.get('username')
        parola = request.POST.get('password')

        utilizator = authenticate(request, username=username, password=parola)

        if utilizator is not None:
            login(request, utilizator)
            # După login, Force2FAMiddleware redirecționează automat
            # la /otp/configurare/ sau /otp/verificare/
            return redirect('/dashboard/')
        else:
            eroare = "Username sau parolă incorecte."

    return render(request, 'cases/autentificare.html', {'eroare': eroare})


def view_logout(request):
    logout(request)
    return redirect('/autentificare/')


@login_required
def view_configurare_otp(request):
    """
    Generează secretul TOTP și afișează QR code-ul.
    Utilizatorul scanează QR-ul cu Aegis/Google Authenticator
    și confirmă cu primul cod generat.
    """
    utilizator = request.user

    # Obține sau creează un TOTPDevice pentru acest utilizator
    device_existent = TOTPDevice.objects.filter(
        user=utilizator, confirmed=True
    ).first()

    if device_existent:
        # 2FA deja configurat — redirecționează
        return redirect('/dashboard/')

    # Creează un device neconfirmat (provizoriu, până la confirmare)
    device, creat = TOTPDevice.objects.get_or_create(
        user=utilizator,
        confirmed=False,
        defaults={'name': f'Dispozitiv {utilizator.username}'}
    )

    # Generează URL-ul pentru QR code (format otpauth://)
    otp_url = device.config_url

    # Generează imaginea QR și o convertește în base64 pentru template
    qr = qrcode.make(otp_url)
    buffer = BytesIO()
    qr.save(buffer, format='PNG')
    qr_base64 = base64.b64encode(buffer.getvalue()).decode()

    if request.method == 'POST':
        cod = request.POST.get('cod_otp')
        # Verifică codul introdus față de device-ul provizoriu
        if device.verify_token(cod):
            device.confirmed = True
            device.save()
            utilizator.otp_configurat = True
            utilizator.save()
            # Marchează sesiunea ca verificată OTP imediat după configurare
            from django_otp import login as otp_login
            otp_login(request, device)
            return redirect('/dashboard/')
        else:
            return render(request, 'cases/configurare_otp.html', {
                'qr_base64': qr_base64,
                'eroare': 'Cod incorect. Încearcă din nou.'
            })

    return render(request, 'cases/configurare_otp.html', {
        'qr_base64': qr_base64
    })


@login_required
def view_verificare_otp(request):
    """
    Pasul 2 din autentificare: codul TOTP.
    Apelat de Force2FAMiddleware după login cu parolă.
    """
    eroare = None

    if request.method == 'POST':
        cod = request.POST.get('cod_otp')

        # Caută toate device-urile confirmate ale utilizatorului
        for device in devices_for_user(request.user):
            if device.verify_token(cod):
                # Marchează sesiunea ca verificată OTP
                from django_otp import login as otp_login
                otp_login(request, device)
                return redirect('/dashboard/')

        eroare = "Cod incorect sau expirat."

    return render(request, 'cases/verificare_otp.html', {'eroare': eroare})


@login_required
def view_dashboard(request):
    """Dashboard minimal — îl extindem în etapele următoare."""
    from cases.models import Dosar
    dosare_recente = Dosar.objects.order_by('-data_deschiderii')[:5]
    return render(request, 'cases/dashboard.html', {
        'dosare_recente': dosare_recente,
        'utilizator': request.user
    })

@login_required
def lista_dosare(request):
    """
    Afișează lista paginată a dosarelor cu căutare și filtrare.
    Demonstrează: QuerySet lazy, Q objects, Paginator.
    """
    # Pornim cu toate dosarele, ordonate descrescător după dată
    queryset = Dosar.objects.select_related(
        'procuror_caz', 'ofiter_caz'
    ).order_by('-data_deschiderii')
    # select_related face JOIN în SQL și aduce datele utilizatorilor
    # legați prin FK într-o singură interogare, în loc de N interogări separate
    # (problema N+1: fără select_related, pentru 50 dosare → 51 interogări SQL)

    # Căutare full-text
    termen = request.GET.get('q', '').strip()
    if termen:
        termen_ascii = curata_diacritice(termen)
        queryset = queryset.filter(
            Q(numar_unic__icontains=termen) |
            Q(infractiune_cercetata_ascii__icontains=termen_ascii) |
            Q(parti_implicate__nume_complet_ascii__icontains=termen_ascii)
        )

    # Filtru după stare
    stare = request.GET.get('stare', '')
    if stare:
        queryset = queryset.filter(stare=stare)

    # Paginare — 10 dosare per pagină
    paginator = Paginator(queryset, 10)
    numar_pagina = request.GET.get('page', 1)
    page_obj = paginator.get_page(numar_pagina)
    # get_page() e mai sigur decât page() — dacă numărul e invalid
    # (ex: 'abc' sau pagina 999 din 5), returnează prima/ultima pagină
    # în loc să ridice excepție

    return render(request, 'cases/lista_dosare.html', {
        'page_obj': page_obj,
        'termen': termen,
        'stare': stare,
        'stari': Dosar.StareDosar.choices,  # pentru dropdown-ul de filtrare
    })


@login_required
def detalii_dosar(request, pk):
    """
    Afișează detaliile complete ale unui dosar.
    pk vine din URL: /dosare/5/ → pk=5
    """
    from django.shortcuts import get_object_or_404
    from documents.models import ActUrmarire
    
    dosar = get_object_or_404(Dosar, pk=pk)
    # get_object_or_404: dacă dosarul nu există → returnează automat
    # pagina 404, în loc să ridice excepție DoesNotExist neprinsă

    parti = dosar.parti_implicate.all()
    infractiuni = dosar.infractiuni.all()
    stadii = dosar.stadii.order_by('-data')
    acte = dosar.documente.select_related('autor', 'semnat_de').all()

    return render(request, 'cases/detalii_dosar.html', {
        'dosar': dosar,
        'parti': parti,
        'infractiuni': infractiuni,
        'stadii': stadii,
        'acte': acte,
    })


@login_required
def dosar_nou(request):
    """
    Formular pentru crearea unui dosar nou.
    Demonstrează: procesarea manuală a formularului POST.
    În Etapa 6 vom introduce Django Forms pentru validare automată.
    """
    eroare = None

    if request.method == 'POST':
        numar_unic = request.POST.get('numar_unic', '').strip()
        infractiune = request.POST.get('infractiune_cercetata', '').strip()
        descriere = request.POST.get('descriere', '').strip()

        if not numar_unic or not infractiune:
            eroare = "Numărul unic și infracțiunea sunt obligatorii."
        elif Dosar.objects.filter(numar_unic=numar_unic).exists():
            eroare = f"Există deja un dosar cu numărul {numar_unic}."
        else:
            dosar = Dosar.objects.create(
                numar_unic=numar_unic,
                infractiune_cercetata=infractiune,
                descriere=descriere,
                procuror_caz=request.user,
            )
            return redirect('detalii_dosar', pk=dosar.pk)

    return render(request, 'cases/dosar_nou.html', {'eroare': eroare})

@login_required
@require_POST
def proceseaza_ocr(request):
    """
    Primește o imagine prin AJAX POST și returnează datele extrase ca JSON.
    
    @require_POST — refuză orice request care nu e POST (GET, PUT etc.)
    Returnează JSON în loc de HTML — e apelat din JavaScript, nu din browser.
    """
    if 'imagine' not in request.FILES:
        return JsonResponse({
            'succes': False,
            'eroare': 'Nicio imagine încărcată.'
        }, status=400)
    
    fisier = request.FILES['imagine']
    
    # Validare tip fișier — doar imagini
    extensii_permise = ['.jpg', '.jpeg', '.png']
    import os
    ext = os.path.splitext(fisier.name)[1].lower()
    if ext not in extensii_permise:
        return JsonResponse({
            'succes': False,
            'eroare': f'Format neacceptat: {ext}. Folosește JPG sau PNG.'
        }, status=400)
    
    rezultat = proceseaza_act_identitate(fisier)
    return JsonResponse(rezultat)

@login_required
def parte_noua(request, dosar_pk):
    """
    GET: afișează formularul cu opțiune OCR
    POST: salvează persoana în baza de date
    """
    from django.shortcuts import get_object_or_404
    dosar = get_object_or_404(Dosar, pk=dosar_pk)

    if request.method == 'POST':
        nume = request.POST.get('nume_complet', '').strip()
        cnp = request.POST.get('cnp', '').strip()
        calitate = request.POST.get('calitate', '')
        adresa = request.POST.get('adresa', '').strip()
        email = request.POST.get('email', '').strip()

        if not nume:
            return render(request, 'cases/parte_noua.html', {
                'dosar': dosar,
                'eroare': 'Numele este obligatoriu.',
                'calitati': ParteImplicata.Calitate.choices,
                'date_initiale': request.POST,
            })

        ParteImplicata.objects.create(
            dosar=dosar,
            nume_complet=nume,
            cnp=cnp or None,
            calitate=calitate,
            adresa=adresa or None,
            email=email or None,
        )
        return redirect('detalii_dosar', pk=dosar.pk)

    return render(request, 'cases/parte_noua.html', {
        'dosar': dosar,
        'calitati': ParteImplicata.Calitate.choices,
        'date_initiale': {},
    })

@login_required
def harta_infractionalitate(request):
    """
    Afișează harta cu toate infracțiunile geocodate.
    
    View-ul furnizează datele ca JSON embedded în template —
    Leaflet.js le citește și plasează markerii.
    """
    from cases.models import Infractiune

    # Doar infracțiunile cu coordonate geocodate
    infractiuni = Infractiune.objects.filter(
        latitudine__isnull=False,
        longitudine__isnull=False
    ).select_related('dosar')

    # Construim lista de markeri pentru Leaflet
    markeri = []
    for inf in infractiuni:
        markeri.append({
            'lat': inf.latitudine,
            'lon': inf.longitudine,
            'incadrare': inf.incadrare_juridica,
            'adresa': inf.adresa_comiterii or '—',
            'dosar_numar': inf.dosar.numar_unic,
            'dosar_url': f'/dosare/{inf.dosar.pk}/',
            'data': inf.data_comiterii.strftime('%d.%m.%Y') if inf.data_comiterii else '—',
        })

    return render(request, 'cases/harta.html', {
        # json.dumps convertește lista Python în string JSON
        # safe=False permite serializarea listelor (nu doar dicts)
        'markeri_json': json.dumps(markeri, ensure_ascii=False),
        'total': len(markeri),
    })

@login_required
@require_POST
def semneaza_document(request, document_pk):
    """
    Aplică semnătură digitală PAdES pe un ActUrmarire PDF.
    
    Flux identic cu cms_penal:
    1. Verificări de permisiuni și format
    2. Verificare parolă (confirmare identitate)
    3. Generare credențiale dacă lipsesc
    4. Decriptare cheie privată
    5. Semnare cu PdfSigner + ștampilă vizuală
    6. Salvare fișier semnat și actualizare model
    """
    import io
    import os
    from django.core.files.base import ContentFile
    from django.shortcuts import get_object_or_404
    from cryptography.fernet import Fernet
    from cryptography.hazmat.primitives.serialization import load_pem_private_key
    from asn1crypto import pem, keys as asn1_keys, x509 as asn1_x509
    from pyhanko.sign import signers
    from pyhanko.sign.fields import SigFieldSpec, append_signature_field
    from pyhanko.pdf_utils.incremental_writer import IncrementalPdfFileWriter
    from pyhanko.stamp import text
    from documents.models import ActUrmarire
    from cases.pki import genereaza_credentiale_utilizator
    from cases.utils import curata_diacritice

    act = get_object_or_404(ActUrmarire, pk=document_pk)
    dosar = act.dosar
    user = request.user

    # Verificare 1: permisiuni
    if not act.are_drepturi_editare(user):
        return JsonResponse({
            'succes': False,
            'eroare': 'Nu aveți dreptul să semnați acest document.'
        }, status=403)

    # Verificare 2: format PDF
    if not act.fisier.name.lower().endswith('.pdf'):
        return JsonResponse({
            'succes': False,
            'eroare': 'Doar documentele PDF pot fi semnate digital.'
        }, status=400)

    # Verificare 3: deja semnat
    if act.este_semnat:
        return JsonResponse({
            'succes': False,
            'eroare': 'Documentul este deja semnat.'
        }, status=400)

    # Verificare 4: parolă utilizator
    parola_introdusa = request.POST.get('parola_semnatura', '')
    if not user.check_password(parola_introdusa):
        return JsonResponse({
            'succes': False,
            'eroare': 'Parolă incorectă. Autorizarea a eșuat.'
        }, status=403)

    # Generează credențiale dacă utilizatorul nu le are încă
    if not user.cheie_privata_criptata or not user.certificat_pem:
        genereaza_credentiale_utilizator(user)
        user.refresh_from_db()

    try:
        # Decriptează cheia privată din DB
        f = Fernet(settings.FERNET_KEY.encode()
                   if isinstance(settings.FERNET_KEY, str)
                   else settings.FERNET_KEY)
        cheie_privata_pem = f.decrypt(bytes(user.cheie_privata_criptata))

        # Încarcă obiectele criptografice cu asn1crypto
        # (același mod ca în cms_penal)
        _, _, priv_der_bytes = pem.unarmor(cheie_privata_pem)
        cheie_privata = asn1_keys.PrivateKeyInfo.load(priv_der_bytes)

        cert_bytes = user.certificat_pem.encode('utf-8')
        _, _, cert_der_bytes = pem.unarmor(cert_bytes)
        certificat = asn1_x509.Certificate.load(cert_der_bytes)

        # Construiește semnatarul pyHanko
        semnatar = signers.SimpleSigner(
            signing_cert=certificat,
            signing_key=cheie_privata,
            cert_registry=None,
        )

        # Deschide PDF-ul în memorie
        pdf_stream = act.fisier.open('rb')
        pdf_bytes = pdf_stream.read()
        pdf_stream.close()

        in_out_buffer = io.BytesIO(pdf_bytes)
        pdf_writer = IncrementalPdfFileWriter(in_out_buffer, strict=False)

        # Câmpul vizual de semnătură — o singură dată, pe ultima pagină
        nume_camp = f'Semnatura_{user.username}'
        append_signature_field(
            pdf_writer,
            SigFieldSpec(
                sig_field_name=nume_camp,
                on_page=-1,           # ultima pagină
                box=(320, 40, 550, 120)
            )
        )

        # Ștampila vizuală — text cu diacritice curățate
        nume_afisare = curata_diacritice(
            user.get_full_name() or user.username
        )
        stil_stampila = text.TextStampStyle(
            stamp_text=(
                f'SEMNAT DIGITAL\n'
                f'Semnatar: {nume_afisare}\n'
                f'Data: %(ts)s\n'
                f'Parchet CMS Demo'
            )
        )

        # PdfSigner — combină metadata + semnatar + ștampilă
        # Acesta e API-ul corect: stamp_style se pasează la PdfSigner,
        # nu la sign_pdf() — de aceea varianta anterioară nu funcționa
        pdf_signer = signers.PdfSigner(
            signers.PdfSignatureMetadata(
                field_name=nume_camp,
                reason='Semnătură digitală aprobată',
                location='CMS Demo Parchet',
            ),
            signer=semnatar,
            stamp_style=stil_stampila,
        )

        # Aplică semnătura în buffer (in_place=True — modifică buffer-ul)
        pdf_signer.sign_pdf(pdf_writer, in_place=True)

        # Salvează fișierul semnat
        in_out_buffer.seek(0)
        nume_original, extensie = os.path.splitext(
            os.path.basename(act.fisier.name)
        )
        nume_fisier_semnat = f"{nume_original}_semnat{extensie}"

        act.fisier_semnat.save(
            nume_fisier_semnat,
            ContentFile(in_out_buffer.read()),
            save=False
        )

        act.este_semnat = True
        act.semnat_de = user
        act.data_semnarii = timezone.now()
        act.save()

        return JsonResponse({
            'succes': True,
            'mesaj': f'Document semnat cu succes de {user.get_full_name() or user.username}.',
            'data_semnarii': act.data_semnarii.strftime('%d.%m.%Y %H:%M'),
            'semnat_de': user.get_full_name() or user.username,
        })

    except Exception as e:
        import logging
        logging.error(
            f"Eroare semnare act {document_pk} de {user.username}: "
            f"{type(e).__name__}: {str(e)}",
            exc_info=True
        )
        return JsonResponse({
            'succes': False,
            'eroare': 'Eroare la semnarea documentului. Verificați că fișierul PDF este valid.'
        }, status=500)