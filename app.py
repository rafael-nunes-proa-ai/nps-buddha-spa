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

    # =========================================================================
    # VALIDAÇÃO: EVITAR REPROCESSAMENTO
    # =========================================================================
    
    # DESABILITADO TEMPORARIAMENTE - React Flow está em loop infinito
    # TODO: Corrigir no React Flow para reconhecer opções e parar de reenviar
    # Verifica se a última mensagem do usuário é igual à mensagem atual
    # Isso evita que o React Flow reenvie a mesma mensagem após receber opções
    if False and len(history) > 0:
        print(f"🔍 DEBUG - Verificando histórico para reprocessamento...")
        print(f"🔍 DEBUG - Total de mensagens no histórico: {len(history)}")
        
        last_user_message = None
        # Procura a última mensagem do usuário no histórico
        for i, msg in enumerate(reversed(history)):
            # Debug: mostra tipo e atributos da mensagem
            print(f"🔍 DEBUG - Mensagem {i}: type={type(msg).__name__}")
            
            # Verifica se é ModelRequest com UserPromptPart
            if hasattr(msg, 'parts') and msg.parts:
                for part in msg.parts:
                    part_type = type(part).__name__
                    print(f"🔍 DEBUG - Mensagem {i} tem part: {part_type}")
                    
                    if part_type == 'UserPromptPart':
                        last_user_message = part.content
                        print(f"✅ DEBUG - Encontrada última mensagem do usuário: {last_user_message}")
                        break
                
                if last_user_message:
                    break
        
        # Se a mensagem atual é igual à última mensagem do usuário
        if last_user_message and last_user_message == message:
            print("=" * 80)
            print("⚠️  REPROCESSAMENTO DETECTADO!")
            print(f"Mensagem atual: {message}")
            print(f"Última mensagem do usuário: {last_user_message}")
            print("� Retornando última resposta (opções) novamente")
            print("=" * 80)
            
            # Busca a última resposta do modelo no histórico (as opções)
            for msg in reversed(history):
                if hasattr(msg, 'parts') and msg.parts:
                    for part in msg.parts:
                        if type(part).__name__ == 'TextPart':
                            # Tenta parsear como JSON de opções
                            try:
                                content = part.content
                                # Remove markdown se existir
                                if content.startswith("```json"):
                                    content = content.replace("```json", "").replace("```", "").strip()
                                elif content.startswith("```"):
                                    content = content.replace("```", "").strip()
                                
                                parsed = json.loads(content)
                                if isinstance(parsed, dict) and "generic" in parsed:
                                    print("✅ Retornando opções do histórico")
                                    return parsed
                            except:
                                pass
            
            # Se não encontrou opções no histórico, retorna mensagem simples
            return {
                "response": "Por favor, selecione uma das opções acima."
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
    
    # Adiciona mensagem do usuário ao histórico ANTES de executar o agente
    from pydantic_ai.messages import ModelRequest, UserPromptPart
    user_message = ModelRequest(parts=[UserPromptPart(content=message)])
    add_messages(conversation_id, [user_message])
    print(f"✅ Mensagem do usuário adicionada ao histórico")
    
    # Executa o agente NPS
    result = await nps_agent.run(
        message,
        message_history=history,
        deps=deps
    )
    
    # =========================================================================
    # EXTRAÇÃO E PARSING DO OUTPUT
    # =========================================================================
    
    # Extrai output do resultado do agente
    output_raw = None
    try:
        output_raw = result.data if hasattr(result, 'data') and result.data else result.output
    except:
        output_raw = result.output
    
    # Se output for string JSON, tenta parsear para dict
    output_final = output_raw
    if isinstance(output_raw, str):
        # Remove formatação markdown se existir (```json ... ```)
        cleaned_output = output_raw.strip()
        if cleaned_output.startswith("```json"):
            cleaned_output = cleaned_output.replace("```json", "").replace("```", "").strip()
        elif cleaned_output.startswith("```"):
            cleaned_output = cleaned_output.replace("```", "").strip()
        
        try:
            parsed_output = json.loads(cleaned_output)
            # Se conseguiu parsear e tem 'generic', usa o objeto parseado
            if isinstance(parsed_output, dict) and "generic" in parsed_output:
                print("🔄 Output era JSON string - parseado para dict")
                output_final = parsed_output
        except json.JSONDecodeError:
            # Se não conseguir parsear, mantém como string
            pass
    
    # =========================================================================
    # SALVAR HISTÓRICO
    # =========================================================================
    
    add_messages(conversation_id, result.new_messages())
    
    # =========================================================================
    # VERIFICAR SE SESSÃO FOI ENCERRADA
    # =========================================================================
    
    session_after = get_session(conversation_id)
    is_session_deleted = session_after is None
    
    if is_session_deleted:
        print("🔴 Sessão foi deletada (encerramento via tool). Retornando resposta final.")
        print("🚩 Flag finalizar_sessao: TRUE")
        print("✅ NPS - Pesquisa encerrada")
        print("=" * 80)
        
        # Verifica se é dict com generic (opções)
        is_option_response = isinstance(output_final, dict) and "generic" in output_final
        
        if is_option_response:
            print("📋 Resposta contém opções (formato output.generic)")
            print(f"📤 Retornando objeto direto com finalizar_sessao")
            # Adiciona flag de finalização ao objeto
            output_final["finalizar_sessao"] = True
            return output_final
        
        # Resposta de texto com flag de finalização
        response_text = {
            "response": str(output_final),
            "finalizar_sessao": True
        }
        return response_text
    
    # =========================================================================
    # DEBUG E PREPARAÇÃO DO RETORNO
    # =========================================================================
    
    print(f"✅ NPS - Resposta: {output_final}")
    print(f"🔍 DEBUG - Tipo do output: {type(output_final)}")
    
    is_dict = isinstance(output_final, dict)
    print(f"🔍 DEBUG - É dict? {is_dict}")
    
    if is_dict:
        dict_keys = output_final.keys()
        has_generic = "generic" in output_final
        print(f"🔍 DEBUG - Chaves do dict: {dict_keys}")
        print(f"🔍 DEBUG - Tem 'generic'? {has_generic}")
        print(f"🔍 DEBUG - Conteúdo completo do dict:")
        print(f"   {json.dumps(output_final, ensure_ascii=False, indent=2)}")
    else:
        output_preview = str(output_final)[:200]
        print(f"🔍 DEBUG - Conteúdo (não é dict): {output_preview}")
    
    print("=" * 80)
    
    # =========================================================================
    # RETORNO FINAL
    # =========================================================================
    
    # Verifica se é resposta com opções (formato output.generic)
    is_option_response = isinstance(output_final, dict) and "generic" in output_final
    
    if is_option_response:
        print("📋 Resposta contém opções (formato output.generic)")
        print(f"📤 RETORNO FINAL (dict direto):")
        print(f"   Type: {type(output_final)}")
        print(f"   Content: {json.dumps(output_final, ensure_ascii=False, indent=2)}")
        print("=" * 80)
        return output_final
    
    # Resposta de texto normal com wrapper
    response_text = {
        "response": str(output_final)
    }
    print(f"📤 RETORNO FINAL (texto com wrapper):")
    print(f"   Type: {type(response_text)}")
    print(f"   Content: {json.dumps(response_text, ensure_ascii=False, indent=2)}")
    print("=" * 80)
    return response_text


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
