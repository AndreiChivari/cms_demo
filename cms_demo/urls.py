from django.contrib import admin
from django.urls import path
from django.conf import settings
from django.conf.urls.static import static
from cases import views as cases_views

urlpatterns = [
    path('admin/', admin.site.urls),
    path('autentificare/', cases_views.view_autentificare, name='autentificare'),
    path('logout/', cases_views.view_logout, name='logout'),
    path('otp/configurare/', cases_views.view_configurare_otp, name='configurare_otp'),
    path('otp/verificare/', cases_views.view_verificare_otp, name='verificare_otp'),
    path('dashboard/', cases_views.view_dashboard, name='dashboard'),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)