import re
import pytesseract
from PIL import Image, ImageEnhance, ImageFilter
from django.conf import settings

# Configurează pytesseract să găsească executabilul Tesseract
pytesseract.pytesseract.tesseract_cmd = settings.TESSERACT_CMD


def preprocesare_imagine(imagine_pil):
    """
    Îmbunătățește calitatea imaginii pentru OCR mai precis.
    
    Primește un obiect PIL.Image, returnează tot un PIL.Image
    procesat — grayscale, contrast crescut, filtru de sharpening.
    """
    # Pas 1: Grayscale — elimină culoarea, păstrează intensitatea
    imagine = imagine_pil.convert('L')
    
    # Pas 2: Resize dacă imaginea e prea mică
    # Tesseract funcționează optim la ≥300 DPI
    # Presupunem că o imagine sub 1000px lățime e prea mică
    w, h = imagine.size
    if w < 1000:
        factor = 1000 / w
        imagine = imagine.resize(
            (int(w * factor), int(h * factor)),
            Image.LANCZOS  # algoritm de resize de calitate înaltă
        )
    
    # Pas 3: Crește contrastul — face textul mai distinct
    enhancer = ImageEnhance.Contrast(imagine)
    imagine = enhancer.enhance(2.0)  # factor 2x față de original
    
    # Pas 4: Sharpening — face marginile caracterelor mai clare
    imagine = imagine.filter(ImageFilter.SHARPEN)
    
    return imagine


def extrage_text_din_imagine(fisier_imagine):
    """
    Primește un fișier imagine (obiect Django UploadedFile sau cale),
    aplică preprocesarea și returnează textul brut extras de Tesseract.
    """
    imagine = Image.open(fisier_imagine)
    imagine_procesata = preprocesare_imagine(imagine)
    
    # config Tesseract:
    # --oem 3 = LSTM neural net (cel mai precis mod)
    # --psm 3 = detectare automată layout (pagină completă)
    # -l ron+eng = română + engleză (buletinele pot conține ambele)
    config = '--oem 3 --psm 3 -l ron+eng'
    
    text = pytesseract.image_to_string(imagine_procesata, config=config)
    return text


def extrage_cnp(text):
    """
    Caută un CNP valid în textul extras de OCR.
    Returnează primul CNP găsit sau None.
    
    CNP valid: 13 cifre, prima între 1-8.
    \b = word boundary — previne match în numere mai lungi.
    """
    pattern = r'\b[1-8]\d{12}\b'
    match = re.search(pattern, text)
    return match.group(0) if match else None


def extrage_nume(text):
    """
    Încearcă să extragă numele de pe buletin.
    
    Buletinele românești au câmpul 'Nume' sau 'Prenume' urmat de valoare.
    Regex-ul caută aceste etichete și extrage ce urmează.
    
    Limitare: OCR-ul poate introduce erori în nume — rezultatul
    trebuie verificat de utilizator înainte de salvare.
    """
    # Caută "Nume" sau "Prenume" urmat de litere mari (numele pe CI e cu majuscule)
    pattern_nume = r'(?:Nume|NUME)[:\s]+([A-ZĂÂÎȘȚ\s\-]+)'
    pattern_prenume = r'(?:Prenume|PRENUME)[:\s]+([A-ZĂÂÎȘȚ\s\-]+)'
    
    nume = ''
    prenume = ''
    
    match_nume = re.search(pattern_nume, text)
    if match_nume:
        nume = match_nume.group(1).strip()
    
    match_prenume = re.search(pattern_prenume, text)
    if match_prenume:
        prenume = match_prenume.group(1).strip()
    
    # Combinăm: pe CI apare "Nume Prenume"
    if nume and prenume:
        return f"{nume} {prenume}"
    return nume or prenume or None


def extrage_adresa(text):
    """
    Încearcă să extragă adresa de domiciliu.
    Caută eticheta 'Domiciliu' sau 'Adresa' și extrage ce urmează.
    """
    pattern = r'(?:Domiciliu|DOMICILIU|Adresa|ADRESA)[:\s]+(.+?)(?:\n|CNP|$)'
    match = re.search(pattern, text, re.DOTALL)
    if match:
        adresa = match.group(1).strip()
        # Eliminăm newline-urile din adresă
        adresa = ' '.join(adresa.split())
        return adresa[:300]  # limita câmpului din model
    return None


def proceseaza_act_identitate(fisier_imagine):
    """
    Funcția principală — coordonează tot fluxul OCR.
    Returnează un dicționar cu datele extrase.
    
    Returnează întotdeauna un dicționar, chiar dacă unele câmpuri
    sunt None — view-ul decide cum gestionează lipsa datelor.
    """
    try:
        text_brut = extrage_text_din_imagine(fisier_imagine)
        
        return {
            'succes': True,
            'text_brut': text_brut,  # util pentru debugging
            'cnp': extrage_cnp(text_brut),
            'nume_complet': extrage_nume(text_brut),
            'adresa': extrage_adresa(text_brut),
        }
    except Exception as e:
        return {
            'succes': False,
            'eroare': str(e),
            'cnp': None,
            'nume_complet': None,
            'adresa': None,
        }