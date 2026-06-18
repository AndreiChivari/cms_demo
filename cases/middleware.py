from django.shortcuts import redirect
from django.conf import settings


# URL-urile la care accesul e permis fără 2FA verificat
# (altfel am crea un redirect loop infinit)
URL_EXCEPTATE = [
    '/autentificare/',
    '/otp/verificare/',
    '/otp/configurare/',
    '/admin/',
]


class Force2FAMiddleware:
    """
    Verifică la fiecare request că utilizatorul autentificat
    a trecut și de pasul de verificare OTP.

    Fără acest middleware, un utilizator cu username+parolă corecte
    ar putea accesa aplicația fără să introducă codul TOTP.
    """
    def __init__(self, get_response):
        # get_response e următorul middleware (sau view-ul final)
        # __init__ se apelează o singură dată la pornirea serverului
        self.get_response = get_response

    def __call__(self, request):
        # __call__ se apelează la FIECARE request

        # 1. Dacă utilizatorul nu e autentificat deloc — lasă Django
        #    să gestioneze (va redirecționa la LOGIN_URL prin @login_required)
        if not request.user.is_authenticated:
            return self.get_response(request)

        # 2. Dacă URL-ul curent e în lista de excepții — lasă să treacă
        path = request.path_info
        if any(path.startswith(url) for url in URL_EXCEPTATE):
            return self.get_response(request)

        # 3. Dacă utilizatorul e autentificat dar nu e verificat OTP
        #    și 2FA este configurat — redirecționează la verificare cod
        if not request.user.is_verified():
            if request.user.otp_configurat:
                return redirect('/otp/verificare/')
            else:
                # 2FA nu e configurat încă — redirecționează la configurare
                return redirect('/otp/configurare/')

        # 4. Totul e în ordine — continuă cu request-ul normal
        return self.get_response(request)