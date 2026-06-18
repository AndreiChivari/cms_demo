from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django_otp.plugins.otp_totp.models import TOTPDevice
from django_otp import devices_for_user
import qrcode
import qrcode.image.svg
from io import BytesIO
import base64


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