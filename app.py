import json
import os
import logging
import uvicorn
import threading
from fastapi import FastAPI, HTTPException, Depends
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
)
from fastapi.middleware.cors import CORSMiddleware

load_dotenv()
app = FastAPI(title="NPS Buddha Spa API", version="1.0.0")

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
        
        # Verifica se sessão existe antes de deletar
        session_antes = get_session(conversation_id)
        if session_antes:
            print(f"📊 Sessão encontrada no banco:")
            print(f"   - Última atualização: {session_antes[3]}")
        else:
            print("⚠️  Sessão não encontrada no banco (pode já ter sido deletada)")
        
        print("🗑️  Deletando sessão do banco de dados...")
        delete_session(conversation_id)
        
        # Verifica se sessão foi realmente deletada
        session_depois = get_session(conversation_id)
        if session_depois is None:
            print("✅ CONFIRMADO: Sessão deletada com sucesso do banco de dados")
        else:
            print("❌ ERRO: Sessão ainda existe no banco após delete_session()")
            print(f"   Dados da sessão: {session_depois}")
        
        print("🚩 Flag finalizar_sessao: TRUE")
        print("📤 Retornando resposta de despedida para React Flow")
        print("=" * 80)
        return {
            "response": "Obrigado por participar da nossa pesquisa de satisfação! 😊\n\nSua opinião é muito importante para nós!",
            "finalizar_sessao": True  # Flag para React Flow encerrar
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
    # PRIMEIRA MENSAGEM: RETORNA OPÇÕES DE NOTA PROFISSIONAL EM JSON
    # =========================================================================
    
    if len(history) == 0:
        print("🎯 PRIMEIRA MENSAGEM - Retornando opções em JSON")
        print("=" * 80)
        
        # Busca nome do cliente e profissional do contexto
        nome_cliente = context.get('nome_cliente', 'Cliente')
        nome_profissional = context.get('nome_profissional', 'profissional')
        
        # Cria JSON de opções (formato AWS Broker)
        opcoes_resposta = {
            "output": {
                "generic": [
                    {
                        "response_type": "option",
                        "title": f"Olá! {nome_cliente}, queremos saber como você se sentiu durante sua experiência com a profissional {nome_profissional}?\nSua opinião é essencial para refletirmos quem faz a diferença e também para evoluirmos onde for preciso.",
                        "options": [
                            {"label": "5", "value": {"input": {"text": "5"}}},
                            {"label": "4", "value": {"input": {"text": "4"}}},
                            {"label": "3", "value": {"input": {"text": "3"}}},
                            {"label": "2", "value": {"input": {"text": "2"}}},
                            {"label": "1", "value": {"input": {"text": "1"}}}
                        ]
                    }
                ]
            },
            "nps_unidade": True  # Flag para React Flow reconhecer
        }
        
        # IMPORTANTE: Salva mensagens no histórico para evitar loop
        from pydantic_ai.messages import ModelRequest, ModelResponse, UserPromptPart, TextPart
        
        user_message = ModelRequest(parts=[UserPromptPart(content=message)])
        bot_message = ModelResponse(parts=[TextPart(content=json.dumps(opcoes_resposta, ensure_ascii=False))])
        add_messages(conversation_id, [user_message, bot_message])
        
        print(f"✅ Opções geradas para primeira mensagem")
        print(f"✅ Mensagens salvas no histórico")
        print(f"📤 RETORNO: {json.dumps(opcoes_resposta, ensure_ascii=False, indent=2)}")
        print("=" * 80)
        
        return opcoes_resposta
    
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
                    print(f"⚠️  Agente retornou JSON - Texto extraído do title")
        except:
            pass
    
    # Salva mensagens no histórico
    add_messages(conversation_id, result.new_messages())
    
    # Verifica se sessão foi deletada (encerramento via tool)
    session_after = get_session(conversation_id)
    if session_after is None:
        print("🔴 Sessão foi deletada (encerramento via tool). Retornando resposta final.")
        print("🚩 Flag finalizar_sessao: TRUE")
        print("✅ NPS - Pesquisa encerrada")
        print("=" * 80)
        return {
            "response": output_text,
            "finalizar_sessao": True  # Flag para React Flow encerrar
        }
    
    # Busca contexto atualizado para incluir flags
    context_updated = session_after[2] or {}
    if isinstance(context_updated, str):
        try:
            context_updated = json.loads(context_updated) if context_updated else {}
        except:
            context_updated = {}
    
    print(f"✅ NPS - Resposta: {output_text}")
    print("=" * 80)
    
    # =========================================================================
    # SEGUNDA PERGUNTA: SE FLAG nps_unidade ESTÁ TRUE, RETORNA OPÇÕES EM JSON
    # =========================================================================
    # Após validar nota do profissional, a tool marca nps_unidade=True
    # Aqui detectamos e retornamos as opções de avaliação da unidade em JSON
    
    if context_updated.get("nps_unidade", False):
        print("🎯 FLAG nps_unidade DETECTADA - Retornando opções da unidade em JSON")
        print("=" * 80)
        
        # Cria JSON de opções para avaliação da unidade (formato AWS Broker)
        opcoes_unidade = {
            "output": {
                "generic": [
                    {
                        "response_type": "option",
                        "title": output_text,  # Usa a resposta do agente como título
                        "options": [
                            {"label": "5", "value": {"input": {"text": "5"}}},
                            {"label": "4", "value": {"input": {"text": "4"}}},
                            {"label": "3", "value": {"input": {"text": "3"}}},
                            {"label": "2", "value": {"input": {"text": "2"}}},
                            {"label": "1", "value": {"input": {"text": "1"}}}
                        ]
                    }
                ]
            },
            "nps_unidade": True  # Flag para React Flow reconhecer
        }
        
        print(f"✅ Opções da unidade geradas")
        print(f"📤 RETORNO: {json.dumps(opcoes_unidade, ensure_ascii=False, indent=2)}")
        print("=" * 80)
        
        return opcoes_unidade
    
    # Retorna resposta normal (sem opções)
    return {
        "response": output_text,
        "nps_unidade": False
    }


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
