from django.contrib import admin
from simple_history.admin import SimpleHistoryAdmin
from .models import ActUrmarire, TrimiterePrinEmail


class TrimiterePrinEmailInline(admin.TabularInline):
    """
    Afișează trimiterile email direct în pagina actului.
    Sunt read-only — jurnalul trimiterilor nu se editează manual.
    """
    model = TrimiterePrinEmail
    extra = 0
    readonly_fields = ['trimis_de', 'trimis_la', 'email_destinatar',
                      'nume_destinatar', 'subiect', 'reusit', 'varianta_trimisa']
    can_delete = False  # nu permitem ștergerea din jurnal


@admin.register(ActUrmarire)
class ActUrmarireAdmin(SimpleHistoryAdmin):
    list_display = ['titlu', 'tip', 'dosar', 'autor', 'data_incarcarii', 'este_semnat']
    list_filter = ['tip', 'este_semnat', 'data_incarcarii']
    search_fields = ['titlu_ascii', 'descriere_scurta_ascii']
    readonly_fields = ['titlu_ascii', 'descriere_scurta_ascii',
                      'data_incarcarii', 'este_semnat', 'semnat_de', 'data_semnarii']
    inlines = [TrimiterePrinEmailInline]


@admin.register(TrimiterePrinEmail)
class TrimiterePrinEmailAdmin(admin.ModelAdmin):
    """
    Jurnalul trimiterilor — doar vizualizare, fără editare.
    Nu folosim SimpleHistoryAdmin aici pentru că înregistrările
    sunt oricum imutabile prin logica aplicației.
    """
    list_display = ['document', 'email_destinatar', 'trimis_de',
                   'trimis_la', 'reusit', 'varianta_trimisa']
    list_filter = ['reusit', 'varianta_trimisa']
    readonly_fields = [f.name for f in TrimiterePrinEmail._meta.get_fields()
                      if hasattr(f, 'name')]
    
    # Nimeni nu poate adăuga sau șterge înregistrări manual din jurnal
    def has_add_permission(self, request):
        return False
    
    def has_delete_permission(self, request, obj=None):
        return False