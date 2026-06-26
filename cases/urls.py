from django.urls import path
from . import views

urlpatterns = [
    # Autentificare
    path('autentificare/', views.view_autentificare, name='autentificare'),
    path('logout/', views.view_logout, name='logout'),
    path('otp/configurare/', views.view_configurare_otp, name='configurare_otp'),
    path('otp/verificare/', views.view_verificare_otp, name='verificare_otp'),

    # Aplicație
    path('dashboard/', views.view_dashboard, name='dashboard'),
    path('dosare/', views.lista_dosare, name='lista_dosare'),
    path('dosare/<int:pk>/', views.detalii_dosar, name='detalii_dosar'),
    path('dosare/nou/', views.dosar_nou, name='dosar_nou'),
    path('ocr/proceseaza/', views.proceseaza_ocr, name='proceseaza_ocr'),
    path('dosare/<int:dosar_pk>/parte-noua/', views.parte_noua, name='parte_noua'),
    path('harta/', views.harta_infractionalitate, name='harta'),
    path('documente/<int:document_pk>/semneaza/', views.semneaza_document, name='semneaza_document'),
]