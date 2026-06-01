import re

def censurar_dados(texto):
    """
    Censura dados de contato (CPF, telefone, links, emails) em uma string.
    Substitui por um aviso para manter a negociação na plataforma.
    """
    if not texto:
        return texto
    
    # Regex para Telefone, CPF, Emails e Links
    padroes = {
        'telefone': r'(\(?\d{2}\)?\s?\d{4,5}-?\d{4})',
        'cpf': r'(\d{3}\.?\d{3}\.?\d{3}-?\d{2})',
        'email': r'([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})',
        'links': r'(https?://[^\s]+|www\.[^\s]+)'
    }
    
    texto_censurado = texto
    for rotulo, padrao in padroes.items():
        texto_censurado = re.sub(padrao, f'[DADO CENSURADO - USE A PLATAFORMA]', texto_censurado, flags=re.IGNORECASE)
    
    return texto_censurado
