import json
import os
import logging
import uvicorn
import threading
from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from dotenv import load_dotenv
from typing import Optional, Union, Any

from agents.agente_nps import nps_agent
from agents.deps import MyDeps
from security.auth import verificar_api_key
from store.database import (
    cleanup_sessions,
    ensure_session,
    get_session,
    get_messages,
    add_messages,
    update_context,
    delete_session,
)

load_dotenv()
app = FastAPI(title="NPS Buddha Spa API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"],  
    allow_headers=["*"],  
)


# ============================================================================
# FUNÇÕES HELPER PARA CADA ETAPA DO FLUXO NPS
# ============================================================================

def retornar_primeira_pergunta(conversation_id: str, message: str, context: dict) -> dict:
    """ETAPA 1: Retorna opções de avaliação do profissional em JSON."""
    print("🎯 PRIMEIRA MENSAGEM - Retornando opções em JSON")
    print("=" * 80)
    
    nome_profissional = context.get('nome_profissional', 'profissional')
    
    opcoes_resposta = {
        "output": {
            "generic": [{
                "response_type": "option",
                "title": f"Queremos saber como você se sentiu durante sua experiência com a profissional {nome_profissional}?\nSua opinião é essencial para refletirmos quem faz a diferença e também para evoluirmos onde for preciso.",
                "options": [
                    {"label": "5", "value": {"input": {"text": "5"}}},
                    {"label": "4", "value": {"input": {"text": "4"}}},
                    {"label": "3", "value": {"input": {"text": "3"}}},
                    {"label": "2", "value": {"input": {"text": "2"}}},
                    {"label": "1", "value": {"input": {"text": "1"}}}
                ]
            }]
        },
        "nota_profissional": True
    }
    
    # Salva mensagens no histórico
    from pydantic_ai.messages import ModelRequest, ModelResponse, UserPromptPart, TextPart
    user_message = ModelRequest(parts=[UserPromptPart(content=message)])
    bot_message = ModelResponse(parts=[TextPart(content=json.dumps(opcoes_resposta, ensure_ascii=False))])
    add_messages(conversation_id, [user_message, bot_message])
    
    print(f"✅ Opções geradas e salvas no histórico")
    print(f"📤 RETORNO: {json.dumps(opcoes_resposta, ensure_ascii=False, indent=2)}")
    print("=" * 80)
    
    return opcoes_resposta


def retornar_segunda_pergunta(output_text: str) -> dict:
    """ETAPA 2: Retorna opções de avaliação da unidade em JSON."""
    print("🎯 FLAG nota_unidade_ativa DETECTADA - Retornando opções da unidade em JSON")
    print("=" * 80)
    
    opcoes_unidade = {
        "output": {
            "generic": [{
                "response_type": "option",
                "title": output_text,
                "options": [
                    {"label": "5", "value": {"input": {"text": "5"}}},
                    {"label": "4", "value": {"input": {"text": "4"}}},
                    {"label": "3", "value": {"input": {"text": "3"}}},
                    {"label": "2", "value": {"input": {"text": "2"}}},
                    {"label": "1", "value": {"input": {"text": "1"}}}
                ]
            }]
        },
        "nota_unidade": True
    }
    
    print(f"✅ Opções da unidade geradas")
    print(f"📤 RETORNO: {json.dumps(opcoes_unidade, ensure_ascii=False, indent=2)}")
    print("=" * 80)
    
    return opcoes_unidade


def retornar_resposta_normal(output_text: str) -> dict:
    """ETAPA 3: Retorna resposta de texto simples (sem opções)."""
    print(f"📤 RETORNO FINAL (sem opções):")
    print(f"  - response: {output_text[:100]}..." if len(output_text) > 100 else f"  - response: {output_text}")
    print("=" * 80)
    
    resposta = {
        "response": output_text,
        "nota_profissional": False,
        "nota_unidade": False
    }
    
    return resposta


# =========================
# Models
# =========================

class ChatRequest(BaseModel):
    conversation_id: str
    message: Union[str, dict, Any]
    phone: Optional[str] = Field(default=None)


# =========================
# Endpoints
# =========================

@app.get("/")
async def read_root():
    return {"service": "NPS Buddha Spa", "status": "running"}


@app.post("/chat")
async def post_chat(req: ChatRequest, api_key: str = Depends(verificar_api_key)):
    """Endpoint principal para processar mensagens do NPS"""
    from store.database import delete_session
    
    message = req.message
    conversation_id = req.conversation_id
    
    # Comando manual de encerramento - Detecta palavras e deleta sessão
    if message and isinstance(message, str) and message.lower() in ["sair", "encerrar"]:
        print("=" * 80)
        print("🔴 FINALIZAR_SESSAO - PALAVRA DE ENCERRAMENTO DETECTADA")
        print(f"Conversation ID: {conversation_id}")
        print(f"Mensagem recebida: {message}")
        print("=" * 80)
        
        print("🗑️  Deletando sessão do banco de dados...")
        delete_session(conversation_id)
        
        session_depois = get_session(conversation_id)
        if session_depois is None:
            print("✅ CONFIRMADO: Sessão deletada com sucesso do banco de dados")
        else:
            print("❌ ERRO: Sessão ainda existe no banco após delete_session()")
        
        print("📤 Retornando resposta de despedida para React Flow")
        print("=" * 80)
        return {
            "response": "Obrigado por participar da nossa pesquisa de satisfação! 😊\n\nSua opinião é muito importante para nós!",
            "finalizar_sessao": True,
            "nota_profissional": False,
            "nota_unidade": False
        }

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
    
    print(f"📊 DEBUG - Contexto atual:")
    print(f"  - nota_profissional: {context.get('nota_profissional', 'N/A')}")
    print(f"  - nota_unidade: {context.get('nota_unidade', 'N/A')}")
    print(f"  - nota_profissional_ativa: {context.get('nota_profissional_ativa', 'N/A')}")
    print(f"  - nota_unidade_ativa: {context.get('nota_unidade_ativa', 'N/A')}")
    print(f"  - mensagem_final_enviada: {context.get('mensagem_final_enviada', 'N/A')}")
    print(f"  - feedback_texto: {context.get('feedback_texto', 'N/A')}")
    print("=" * 80)
    
    # =========================================================================
    # VERIFICAÇÃO: Se mensagem final já foi enviada, encerra na próxima mensagem
    # =========================================================================
    if context.get("mensagem_final_enviada") == True:
        print("🎯 MENSAGEM FINAL JÁ FOI ENVIADA - Encerrando sessão")
        print(f"   Nota profissional: {context.get('nota_profissional')}")
        print(f"   Nota unidade: {context.get('nota_unidade')}")
        print("=" * 80)
        
        delete_session(conversation_id)
        
        return {
            "response": "Obrigado por participar da nossa pesquisa de satisfação! 😊\n\nSua opinião é muito importante para nós!",
            "finalizar_sessao": True,
            "nota_profissional": False,
            "nota_unidade": False
        }

    # Prepara dependências
    context.setdefault("session_id", conversation_id)
    deps = MyDeps(**context)
    
    print("=" * 80)
    print("📨 NPS - Nova mensagem")
    print(f"Conversation ID: {conversation_id}")
    print(f"Mensagem: {message}")
    print(f"Histórico: {len(history)} mensagens")
    print("=" * 80)
    
    # =========================================================================
    # ETAPA 1: PRIMEIRA MENSAGEM - OPÇÕES PROFISSIONAL
    # =========================================================================
    if len(history) == 0:
        return retornar_primeira_pergunta(conversation_id, message, context)
    
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
    
    # Se o agente retornou JSON em vez de texto, extrai o texto do title
    if output_text.startswith('{') and '"output"' in output_text:
        try:
            parsed = json.loads(output_text)
            if 'output' in parsed and 'generic' in parsed['output']:
                generic = parsed['output']['generic'][0]
                if 'title' in generic:
                    output_text = generic['title']
                    print(f"⚠️  Agente retornou JSON - Texto extraído do 'title'")
                elif 'text' in generic:
                    output_text = generic['text']
                    print(f"⚠️  Agente retornou JSON - Texto extraído do 'text'")
        except:
            pass
    
    # Salva mensagens no histórico
    add_messages(conversation_id, result.new_messages())
    
    # Busca contexto atualizado para incluir flags
    session_after = get_session(conversation_id)
    context_updated = session_after[2] or {}
    if isinstance(context_updated, str):
        try:
            context_updated = json.loads(context_updated) if context_updated else {}
        except:
            context_updated = {}
    
    print(f"✅ NPS - Resposta: {output_text}")
    print("=" * 80)
    
    # =========================================================================
    # ETAPA 2: SEGUNDA PERGUNTA - OPÇÕES UNIDADE
    # =========================================================================
    # Após validar nota do profissional, a tool marca nota_unidade_ativa=True
    # Aqui detectamos e retornamos as opções de avaliação da unidade em JSON
    if context_updated.get("nota_unidade_ativa", False):
        return retornar_segunda_pergunta(output_text)
    
    # =========================================================================
    # RESPOSTA NORMAL (SEM OPÇÕES)
    # =========================================================================
    return retornar_resposta_normal(output_text)


# =========================
# Server Startup
# =========================

if __name__ == "__main__":
    try:
        # Inicia thread de limpeza de sessões
        session_check_thread = threading.Thread(target=cleanup_sessions, daemon=True)
        session_check_thread.start()
        
        port = int(os.getenv("PORT", 8082))
        workers = int(os.getenv("WORKERS", 1))
        reload = bool(os.getenv("RELOAD", False))
        
        print(f"🚀 Starting NPS server on port {port}")
        print(f"   Workers: {workers}")
        print(f"   Reload: {reload}")

        uvicorn.run(
            "app:app",
            host="0.0.0.0",
            port=port,
            workers=workers if not reload else 1,
            log_level="info",
            proxy_headers=True,
            timeout_keep_alive=30,
            reload=reload,
        )
    except Exception as e:
        logging.error(f"Erro ao iniciar o servidor: {e}")
        raise
