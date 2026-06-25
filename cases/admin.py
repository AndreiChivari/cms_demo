from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from simple_history.admin import SimpleHistoryAdmin
from .models import (
    CustomUser, Dosar, ParteImplicata,
    Infractiune, StadiuCercetare, MasuraPreventiva
)


# ——— Inline-uri ———————————————————————————————————————————

class ParteImplicataInline(admin.TabularInline):
    """
    Afișează părțile implicate direct în pagina dosarului.
    extra=1 înseamnă că apare un formular gol în plus pentru adăugare rapidă.
    """
    model = ParteImplicata
    extra = 1
    fields = ['nume_complet', 'cnp', 'calitate', 'email']


class InfractiuneInline(admin.TabularInline):
    model = Infractiune
    extra = 1
    fields = ['incadrare_juridica', 'data_comiterii', 'adresa_comiterii']


class StadiuCercetareInline(admin.TabularInline):
    model = StadiuCercetare
    extra = 0          # fără formular gol — stadiile se adaugă deliberat
    fields = ['tip', 'data', 'observatii']
    readonly_fields = ['data']   # data se setează la creare, nu se modifică


# ——— ModelAdmin-uri ————————————————————————————————————————

@admin.register(CustomUser)
class CustomUserAdmin(UserAdmin):
    """
    Extinde UserAdmin standard cu câmpurile noastre custom.
    UserAdmin are deja logică pentru parole, permisiuni, grupuri.
    Dacă am folosi ModelAdmin simplu, am pierde toate astea.
    """
    # fieldsets controlează cum sunt grupate câmpurile în pagina de editare
    fieldsets = UserAdmin.fieldsets + (
        ('Informații Parchet', {
            'fields': ('functie', 'parafa', 'otp_configurat')
        }),
    )
    # Câmpurile afișate la crearea unui utilizator nou din admin
    add_fieldsets = UserAdmin.add_fieldsets + (
        ('Informații Parchet', {
            'fields': ('functie', 'parafa')
        }),
    )
    list_display = ['username', 'get_full_name', 'functie', 'parafa', 'is_staff']
    list_filter = ['functie', 'is_staff', 'is_active']
    search_fields = ['username', 'first_name', 'last_name', 'parafa']


@admin.register(Dosar)
class DosarAdmin(SimpleHistoryAdmin):
    """
    SimpleHistoryAdmin în loc de ModelAdmin — adaugă automat
    o secțiune 'History' în pagina dosarului cu toate modificările.
    """
    list_display = ['numar_unic', 'infractiune_cercetata', 'stare',
                    'procuror_caz', 'data_deschiderii']
    list_filter = ['stare', 'data_deschiderii']
    search_fields = ['numar_unic', 'infractiune_cercetata_ascii']
    readonly_fields = ['infractiune_cercetata_ascii']
    date_hierarchy = 'data_deschiderii'  # navigator de date în partea de sus
    
    # Inline-urile afișate în pagina dosarului
    inlines = [ParteImplicataInline, InfractiuneInline, StadiuCercetareInline]
    
    # Gruparea câmpurilor în secțiuni vizuale
    fieldsets = (
        ('Date generale', {
            'fields': ('numar_unic', 'stare', 'infractiune_cercetata',
                      'infractiune_cercetata_ascii', 'descriere')
        }),
        ('Echipa dosarului', {
            'fields': ('procuror_caz', 'ofiter_caz')
        }),
        ('Date temporale', {
            'fields': ('data_deschiderii',)
        }),
    )


@admin.register(ParteImplicata)
class ParteImplicataAdmin(SimpleHistoryAdmin):
    list_display = ['nume_complet', 'calitate', 'dosar', 'email']
    list_filter = ['calitate']
    search_fields = ['nume_complet_ascii', 'cnp']
    readonly_fields = ['nume_complet_ascii', 'adresa_ascii']


@admin.register(Infractiune)
class InfractiuneAdmin(SimpleHistoryAdmin):
    list_display = ['incadrare_juridica', 'dosar', 'data_comiterii', 'adresa_comiterii']
    search_fields = ['incadrare_juridica_ascii', 'adresa_comiterii_ascii']
    readonly_fields = ['incadrare_juridica_ascii', 'adresa_comiterii_ascii',
                      'latitudine', 'longitudine']


@admin.register(MasuraPreventiva)
class MasuraPreventivaAdmin(SimpleHistoryAdmin):
    list_display = ['tip', 'parte', 'data_start', 'data_expirare', 'activa']
    list_filter = ['tip', 'activa']
    readonly_fields = ['data_start']


@admin.register(StadiuCercetare)
class StadiuCercetareAdmin(SimpleHistoryAdmin):
    list_display = ['tip', 'dosar', 'data', 'inregistrat_de']
    list_filter = ['tip']
    readonly_fields = ['data']