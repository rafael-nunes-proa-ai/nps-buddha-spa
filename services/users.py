import os
import requests
from dotenv import load_dotenv
import re

load_dotenv()


def limpar_numero(s):
    digits = re.sub(r'\D', '', s)        
    sem_ddi = re.sub(r'^0*55', '', digits)  
    return sem_ddi


def get_user(celular: str) -> dict:
    """Verifica se o número de celular já está cadastrado no sistema

    Args:
        celular (str): Número de celular a ser verificado no formato (XX)XXXXX-XXXX ou XXXXXXXXXXX.

    Returns:
        dic: dicionário com os dados do cadastro do usuário.
    """

    celular = limpar_numero(celular)
    url = f'https://app.bellesoftware.com.br/api/release/controller/IntegracaoExterna/v1.0/cliente/listar?codEstab=1&celular={celular}'
    headers = {
        'Authorization': os.getenv("LABELLE_TOKEN")
    }

    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        data = response.json()
        if 'msg' in data:
            return {"erro": data['msg']}
        else:
            return data
    except Exception as e:
        return {"erro": f'Não foi possível consultar o cadastro no momento {e}'}