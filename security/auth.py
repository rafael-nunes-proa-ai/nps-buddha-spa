import os
from dotenv import load_dotenv
from fastapi import Security, HTTPException
from fastapi.security import APIKeyHeader

load_dotenv()


# Defina sua chave de API
API_KEY = os.getenv("API_KEY") 
API_KEY_NAME = "X-API-KEY" 
api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=True)

def verificar_api_key(api_key: str = Security(api_key_header)):
    """Verifica se a API key recebida é válida."""
    if api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Acesso não autorizado")
    return api_key