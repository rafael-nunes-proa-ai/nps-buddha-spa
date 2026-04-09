import time
from datetime import datetime
import json
import os
import logging
import re
import uvicorn
from fastapi import FastAPI, Request, HTTPException, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from dotenv import load_dotenv
from agents.agente_nps import nps_agent
from dataclasses import dataclass
from fastapi.middleware.cors import CORSMiddleware
from security.auth import verificar_api_key
from typing import List, Dict, Any, Optional, Union
from fastapi.encoders import jsonable_encoder
import threading

from store.database import cleanup_sessions
from agents.deps import MyDeps
from store.database import (
    ensure_session,
    get_session,
    get_messages,
    add_messages,
    update_context,
    update_current_agent,
)

load_dotenv()
app = FastAPI()


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"],  
    allow_headers=["*"],  
)


# =========================
# Models
# =========================
class SessionData(BaseModel):
    session_id: str
    messages: List[Dict[str, Any]]
    current_agent: str
    context: Dict[str, Any]
    last_updated: datetime
    
class ChatRequest(BaseModel):
    conversation_id: str
    message: Union[str, dict, Any]
    phone: Optional[str] = Field(default=None)

AGENTS = {
    "nps_agent": nps_agent
}

# =========================
# Main Chat Endpoint
# =========================

@app.get("/")
async def read_root():
    return {"Hello": "World"}


@app.post("/chat")
async def post_chat(req: ChatRequest, api_key: str = Depends(verificar_api_key)):
    """Endpoint principal para processar mensagens do NPS"""
    
    message = req.message
    conversation_id = req.conversation_id

    # Garante que sessão existe
    ensure_session(conversation_id)

    # Busca dados da sessão
    session = get_session(conversation_id)
    context = session[2] or {}

    # Parse do contexto
    if isinstance(context, str):
        context = context.strip()
        if context == "" or context.lower() == "none":
            context = {}
        else:
            try:
                context = json.loads(context)
            except Exception:
                context = {}

    # Histórico de mensagens
    history = get_messages(conversation_id)

    # Prepara dependências
    context.setdefault("session_id", conversation_id)
    deps = MyDeps(**context)
    
    print("=" * 80)
    print(" NPS - Nova mensagem")
    print(f"Conversation ID: {conversation_id}")
    print(f"Mensagem: {message}")
    print(f"Histórico: {len(history)} mensagens")
    print("=" * 80)
    
    # Executa o agente NPS
    result = await nps_agent.run(
        message,
        message_history=history,
        deps=deps
    )
    
    # Extrai output
    try:
        output_text = result.data if hasattr(result, 'data') and result.data else result.output
        output_text = str(output_text)
    except:
        output_text = str(result.output)
    
    # Salva mensagens no histórico
    add_messages(conversation_id, result.new_messages())
    
    # Verifica se sessão foi deletada (encerramento)
    session_after = get_session(conversation_id)
    if session_after is None:
        print(" NPS - Pesquisa encerrada")
        print("=" * 80)
        return {"response": output_text}
    
    # Busca contexto atualizado para incluir flags
    context_updated = session_after[2] or {}
    if isinstance(context_updated, str):
        try:
            context_updated = json.loads(context_updated) if context_updated else {}
        except:
            context_updated = {}
    
    print(f" NPS - Resposta: {output_text}")
    print("=" * 80)
    
    # Retorna resposta com flag nps_unidade se existir
    return {
        "response": output_text,
        "nps_unidade": context_updated.get("nps_unidade", False)
    }


# =========================
# Server Startup
# =========================
    
    # Output principal
    try:
        output_text = result.data if hasattr(result, 'data') else result.output
        output_text = str(output_text)
    except:
        output_text = str(result)

    # Verifica se há comando de transferência
    transfer_tag = "@transferir_humano"
    transfer_call = False
    if transfer_tag in output_text:
        output_text = output_text.replace(transfer_tag, "").strip()
        transfer_call = True

    clean_data["output"] = output_text
    clean_data["transfer_call"] = transfer_call  # null por padrão se não houver

    # Tenta adicionar informações extras se disponíveis
    try:
        if hasattr(result, '_state') and hasattr(result._state, 'usage'):
            usage = result._state.usage
            clean_data["usage"] = {
                "total_tokens": getattr(usage, 'total_tokens', 0),
                "request_tokens": getattr(usage, 'request_tokens', 0),
                "response_tokens": getattr(usage, 'response_tokens', 0),
            }
    except:
        pass  # Ignora se não conseguir acessar usage
    
    return clean_data


#
#Security
#
# 🔒 Palavras e padrões suspeitos
SQL_KEYWORDS = [
    "select", "insert", "update", "delete", "drop", "alter", "truncate", "union", "exec", "create", "replace",
]
CODE_PATTERNS = [
    # JS specifics
    r"\bconsole\.log\s*\(",      # console.log(...)
    r"\bdocument\.\w+",         # document.xxx
    r"\bwindow\.\w+",           # window.xxx
    r"\bfetch\s*\(",            # fetch(...)
    r"\baxios\.\w+",            # axios.get/post...
    r"\bimport\s+[\w\{\}\*\s,]+from\b",  # import ... from ...
    r"\brequire\s*\(",          # require(...)
    r"\bexport\s+(default|const|function|class)\b",
    r"\bconst\s+\w+\s*=",       # const name =
    r"\blet\s+\w+\s*=",         # let name =
    r"\bvar\s+\w+\s*=",         # var name =
    r"=>",                      # arrow functions

    # Generic function/class/def patterns (Python/JS/other)
    r"\bdef\s+\w+\s*\(",        # def func(
    r"\bclass\s+\w+",           # class Name
    r"[A-Za-z_]\w*\s*\([^)]{0,200}\)\s*;?",  # name(args) optional semicolon - heuristic

    # Dangerous builtins / calls
    r"\beval\s*\(", 
    r"\bexec\s*\(",
    r"os\.system\s*\(",
    r"subprocess\.",
    r"popen\s*\(",
    
    # HTML/script injection
    r"<script.*?>",
    r"```.*?```",               # fenced code blocks (markdown)
]
PROMPT_INJECTION_PATTERNS = [
    # Inglês
    r"ignore\s+your\s+previous\s+instructions",
    r"forget\s+all\s+previous\s+rules",
    r"system\s+prompt",
    r"act\s+as\s+an\s+assistant",
    r"you\s+are\s+no\s+longer\s+chatgpt",
    r"disregard\s+all\s+prior\s+context",
    r"override\s+the\s+system",
    r"developer\s+mode",
    
    # Português
    r"ignore\s+suas\s+instruções\s+anteriores",
    r"esqueça\s+todas\s+as\s+regras\s+anteriores",
    r"prompt\s+do\s+sistema",
    r"aja\s+como\s+um\s+assistente",
    r"você\s+não\s+é\s+mais\s+um\s+assistente",
    r"desconsidere\s+as\s+instruções\s+anteriores",
    r"mude\s+seu\s+comportamento",
    r"modifique\s+suas\s+regras",
    r"finja\s+ser\s+um\s+usuário",
    r"ative\s+modo\s+desenvolvedor",
    r"prompt",
]
# ---- listas para temas não relacionados
POLITICS_WORDS = [
    # English
    "election", "vote", "voting", "president", "government", "congress", "senate", "politician", "party", "impeach",
    # Português
    "eleição", "voto", "votar", "presidente", "governo", "congresso", "senador", "partido", "impeachment", "candidato",
    # (nomes de políticos podem ser adicionados conforme necessário)
]

VIOLENCE_WORDS = [
    # English
    "kill", "murder", "shoot", "stab", "bomb", "explode", "attack", "torture",
    # Português
    "matar", "morte", "assassinar", "atacar", "bomba", "explodir", "tortura", "esfaquear",
]

PROFANITY_WORDS = [
    # English
    "fuck", "shit", "bitch", "damn",
    # Português (palavrões comuns) -- se preferir, pode ofuscar
    "porra", "merda", "caralho", "pqp",
]




# ---- já existentes (exemplos)
SQL_KEYWORDS = [
    "select", "insert", "update", "delete", "drop", "alter", "truncate", "union", "exec", "create", "replace",
]

CODE_PATTERNS = [
    r"\bconsole\.log\s*\(",
    r"\bdocument\.\w+",
    r"\bwindow\.\w+",
    r"\bfetch\s*\(",
    r"\baxios\.\w+",
    r"\bimport\s+[\w\{\}\*\s,]+from\b",
    r"\brequire\s*\(",
    r"\bexport\s+(default|const|function|class)\b",
    r"\bconst\s+\w+\s*=",
    r"\blet\s+\w+\s*=",
    r"\bvar\s+\w+\s*=",
    r"=>",
    r"\bdef\s+\w+\s*\(",
    r"\bclass\s+\w+",
    r"[A-Za-z_]\w*\s*\([^)]{0,200}\)\s*;?",
    r"\beval\s*\(",
    r"\bexec\s*\(",
    r"os\.system\s*\(",
    r"subprocess\.",
    r"popen\s*\(",
    r"<script.*?>",
    r"```.*?```",
]

PROMPT_INJECTION_PATTERNS = [
    # Inglês
    r"ignore\s+your\s+previous\s+instructions",
    r"forget\s+all\s+previous\s+rules",
    r"system\s+prompt",
    r"act\s+as\s+an\s+assistant",
    r"you\s+are\s+no\s+longer\s+chatgpt",
    r"disregard\s+all\s+prior\s+context",
    r"override\s+the\s+system",
    r"developer\s+mode",
    # Português
    r"ignore\s+suas\s+instruções\s+anteriores",
    r"esqueça\s+todas\s+as\s+regras\s+anteriores",
    r"prompt\s+do\s+sistema",
    r"aja\s+como\s+um\s+assistente",
    r"você\s+não\s+é\s+mais\s+um\s+assistente",
    r"desconsidere\s+as\s+instruções\s+anteriores",
    r"mude\s+seu\s+comportamento",
    r"modifique\s+suas\s+regras",
    r"finja\s+ser\s+um\s+usuário",
    r"ative\s+modo\s+desenvolvedor",
]

# ---- listas para temas não relacionados
POLITICS_WORDS = [
    # English
    "election", "vote", "voting", "president", "government", "congress", "senate", "politician", "party", "impeach", "Obama", "Trump", "Biden",
    # Português
    "eleição", "voto", "votar", "presidente", "governo", "congresso", "senador", "partido", "impeachment", "candidato", "Lula", "Bolsonaro",
    # (nomes de políticos podem ser adicionados conforme necessário)
]

VIOLENCE_WORDS = [
    # English
    "kill", "murder", "shoot", "stab", "bomb", "explode", "attack", "torture",
    # Português
    "matar", "morte", "assassinar", "atacar", "bomba", "explodir", "tortura", "esfaquear",
]

PROFANITY_WORDS = [
    # English
    "fuck", "shit", "bitch", "damn",
    # Português (palavrões comuns) -- se preferir, pode ofuscar
    "porra", "merda", "caralho", "pqp",
]

def contains_word_from_list(text: str, words: list) -> bool:
    """Procura qualquer palavra da lista no texto (word-boundary)."""
    for w in words:
        if re.search(r"\b" + re.escape(w) + r"\b", text, flags=re.IGNORECASE):
            return True
    return False

def is_malicious_message(msg: str) -> bool:
    """Verifica se o texto contém SQL, código ou prompt injection."""
    if not isinstance(msg, str):
        return False

    text = msg.strip()
    lower = text.lower()

    # 1) SQL keywords (palavra isolada)
    for kw in SQL_KEYWORDS:
        if re.search(r"\b" + re.escape(kw) + r"\b", lower):
            return True

    # 2) Código / padrões perigosos
    for pattern in CODE_PATTERNS:
        if re.search(pattern, text, flags=re.IGNORECASE | re.DOTALL):
            return True

    # 3) Prompt injection (ing e pt)
    for pattern in PROMPT_INJECTION_PATTERNS:
        if re.search(pattern, lower, flags=re.IGNORECASE):
            return True

    return False

def categorize_unrelated_themes(msg: str) -> Optional[str]:
    """
    Retorna:
      - "politics" se detectar termos relacionados a política,
      - "violence" se detectar violência,
      - "profanity" se detectar palavrões,
      - None se nenhum tema for detectado.
    """
    if not isinstance(msg, str):
        return None
    text = msg.strip()
    lower = text.lower()

    if contains_word_from_list(lower, VIOLENCE_WORDS):
        return "violence"
    if contains_word_from_list(lower, PROFANITY_WORDS):
        return "profanity"
    if contains_word_from_list(lower, POLITICS_WORDS):
        return "politics"
    return None

if __name__ == "__main__":
    try:
        session_check_thread = threading.Thread(target=cleanup_sessions, daemon=True)
        session_check_thread.start()
        port = int(os.getenv("PORT", 8082))
        workers = int(os.getenv("WORKERS", 1))
        reload = bool(os.getenv("RELOAD", False) == True)
        print(f"Starting server on port {port} with {workers} workers and reload={reload}")

        uvicorn.run(
            "app:app",
            host="0.0.0.0",
            port=port,
            workers=workers if not os.getenv("RELOAD") else 1,
            log_level="info",
            proxy_headers=True,
            timeout_keep_alive=30,
            reload=bool(os.getenv("RELOAD")),
        )
    except Exception as e:
        logging.error(f"Erro ao iniciar o servidor: {e}")
        raise