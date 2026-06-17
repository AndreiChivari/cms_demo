def curata_diacritice(text):
    if not text:
        return ""
        
    inlocuiri = {
        'ă': 'a', 'â': 'a', 'î': 'i', 'ș': 's', 'ț': 't',
        'Ă': 'A', 'Â': 'A', 'Î': 'I', 'Ș': 'S', 'Ț': 'T',
        'ş': 's', 'ţ': 't', 'Ş': 'S', 'Ţ': 'T' 
    }
    for ro_char, en_char in inlocuiri.items():
        text = text.replace(ro_char, en_char)
        
    return text