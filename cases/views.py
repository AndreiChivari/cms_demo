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
    
    dosar = get_object_or_404(Dosar, pk=pk)
    # get_object_or_404: dacă dosarul nu există → returnează automat
    # pagina 404, în loc să ridice excepție DoesNotExist neprinsă

    parti = dosar.parti_implicate.all()
    infractiuni = dosar.infractiuni.all()
    stadii = dosar.stadii.order_by('-data')

    return render(request, 'cases/detalii_dosar.html', {
        'dosar': dosar,
        'parti': parti,
        'infractiuni': infractiuni,
        'stadii': stadii,
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