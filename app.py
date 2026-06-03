import json
import os
import logging
import uvicorn
import threading
from fastapi import FastAPI, HTTPException, Depends, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from dotenv import load_dotenv
from typing import Optional, Union, Any

from agents.agente_nps import nps_agent, confirmacao_agent, no_show_agent
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
        "botao_profissional": True
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
        "botao_unidade": True
    }
    
    print(f"✅ Opções da unidade geradas")
    print(f"📤 RETORNO: {json.dumps(opcoes_unidade, ensure_ascii=False, indent=2)}")
    print("=" * 80)
    
    return opcoes_unidade


def retornar_resposta_normal(output_text: str, pesquisa_encerrada: bool = False) -> dict:
    """ETAPA 3: Retorna resposta de texto simples (sem opções)."""
    print(f"📤 RETORNO FINAL (sem opções):")
    print(f"  - response: {output_text[:100]}..." if len(output_text) > 100 else f"  - response: {output_text}")
    if pesquisa_encerrada:
        print("🚩 Flag finalizar_sessao: TRUE")
    print("=" * 80)
    
    resposta = {"response": output_text}
    if pesquisa_encerrada:
        resposta["finalizar_sessao"] = True
    
    return resposta


def retornar_botoes_confirmacao(output_text: str) -> dict:
    """Retorna botões SIM/NÃO para confirmação de agendamento."""
    print("🎯 BOTÕES DE CONFIRMAÇÃO - Retornando opções SIM/NÃO em JSON")
    print("=" * 80)
    
    opcoes = {
        "output": {
            "generic": [{
                "response_type": "option",
                "title": output_text,
                "options": [
                    {"label": "SIM", "value": {"input": {"text": "SIM"}}},
                    {"label": "NÃO", "value": {"input": {"text": "NÃO"}}}
                ]
            }]
        },
        "botao_confirmacao": True
    }
    
    print(f"✅ Botões de confirmação gerados")
    print(f"📤 RETORNO: {json.dumps(opcoes, ensure_ascii=False, indent=2)}")
    print("=" * 80)
    
    return opcoes


def retornar_botoes_reagendar_cancelar(output_text: str) -> dict:
    """Retorna botões Reagendar/Cancelar."""
    print("🎯 BOTÕES REAGENDAR/CANCELAR - Retornando opções em JSON")
    print("=" * 80)
    
    opcoes = {
        "output": {
            "generic": [{
                "response_type": "option",
                "title": output_text,
                "options": [
                    {"label": "Reagendar", "value": {"input": {"text": "Reagendar"}}},
                    {"label": "Cancelar", "value": {"input": {"text": "Cancelar"}}}
                ]
            }]
        },
        "botao_reagendar_cancelar": True
    }
    
    print(f"✅ Botões reagendar/cancelar gerados")
    print(f"📤 RETORNO: {json.dumps(opcoes, ensure_ascii=False, indent=2)}")
    print("=" * 80)
    
    return opcoes


def retornar_botoes_no_show(output_text: str) -> dict:
    """Retorna botões SIM/NÃO para no show."""
    print("🎯 BOTÕES NO SHOW - Retornando opções SIM/NÃO em JSON")
    print("=" * 80)
    
    opcoes = {
        "output": {
            "generic": [{
                "response_type": "option",
                "title": output_text,
                "options": [
                    {"label": "SIM", "value": {"input": {"text": "SIM"}}},
                    {"label": "NÃO", "value": {"input": {"text": "NÃO"}}}
                ]
            }]
        },
        "botao_confirmacao_no_show": True
    }
    
    print(f"✅ Botões no show gerados")
    print(f"📤 RETORNO: {json.dumps(opcoes, ensure_ascii=False, indent=2)}")
    print("=" * 80)
    
    return opcoes


# =========================
# Models
# =========================

class ChatRequest(BaseModel):
    conversation_id: str
    message: Union[str, dict, Any]
    phone: Optional[str] = Field(default=None)
    tituloHSM: Optional[str] = Field(default=None)
    respostaHSM: Optional[str] = Field(default=None)


# =========================
# Endpoints
# =========================

@app.get("/")
async def read_root():
    return {"service": "NPS Buddha Spa", "status": "running"}


@app.post("/chat")
async def post_chat(req: ChatRequest, background_tasks: BackgroundTasks, api_key: str = Depends(verificar_api_key)):
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
            "botao_profissional": False,
            "botao_unidade": False
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
        print("=" * 80)
        print("🎯 MENSAGEM FINAL JÁ FOI ENVIADA - Encerrando sessão")
        print(f"   Nota profissional: {context.get('nota_profissional')}")
        print(f"   Nota unidade: {context.get('nota_unidade')}")
        print(f"   Feedback: {context.get('resposta_feedback_unidade', 'N/A')}")
        print("🗑️  Deletando sessão do banco de dados...")
        
        delete_session(conversation_id)
        
        session_depois = get_session(conversation_id)
        if session_depois is None:
            print("✅ CONFIRMADO: Sessão deletada com sucesso")
        else:
            print("❌ ERRO: Sessão ainda existe após delete_session()")
        
        print("🚩 Flag finalizar_sessao: TRUE")
        retorno_final = {
            "response": "Obrigado por participar da nossa pesquisa de satisfação! 😊\n\nSua opinião é muito importante para nós!",
            "nota_profissional": context.get('nota_profissional'),
            "nota_unidade": context.get('nota_unidade'),
            "resposta_feedback_unidade": context.get('resposta_feedback_unidade'),
            "confirmou_agendamento": context.get('confirmou_agendamento'),
            "finalizar_sessao": True,
            "botao_profissional": False,
            "botao_unidade": False
        }
        print(f"📤 RETORNO FINAL: {json.dumps(retorno_final, ensure_ascii=False, indent=2)}")
        print("=" * 80)
        return retorno_final

    # ROTEAMENTO DE AGENTES BASEADO EM tituloHSM
    # Adiciona tituloHSM e respostaHSM ao contexto se fornecidos
    if req.tituloHSM:
        context["tituloHSM"] = req.tituloHSM
        update_context(conversation_id, {"tituloHSM": req.tituloHSM})
    
    if req.respostaHSM:
        context["respostaHSM"] = req.respostaHSM
        update_context(conversation_id, {"respostaHSM": req.respostaHSM})
    
    # Seleciona o agente baseado no tituloHSM
    titulo_hsm = context.get("tituloHSM") or req.tituloHSM
    
    if titulo_hsm == "nps_buddha":
        agente_atual = nps_agent
        nome_agente = "NPS"
        print("🎯 Agente selecionado: NPS")
    
    elif titulo_hsm == "confirmacao_buddha_v3":
        agente_atual = confirmacao_agent
        nome_agente = "CONFIRMAÇÃO"
        print("🎯 Agente selecionado: CONFIRMAÇÃO")
    
    elif titulo_hsm == "no_show_sem_consumo_voucher":
        agente_atual = no_show_agent
        nome_agente = "NO SHOW"
        print("🎯 Agente selecionado: NO SHOW")
    
    else:
        # Fallback para NPS se não houver tituloHSM
        agente_atual = nps_agent
        nome_agente = "NPS (fallback)"
        print("⚠️  Nenhum tituloHSM fornecido - usando NPS como fallback")
    
    # Prepara dependências
    context.setdefault("session_id", conversation_id)
    deps = MyDeps(**context)
    
    # Se message estiver vazio e respostaHSM existir, usa respostaHSM como mensagem
    # Isso só se aplica aos agentes confirmacao e no_show (não ao NPS)
    mensagem_vazia = (
        not message or 
        message == {} or 
        message == "" or 
        (isinstance(message, dict) and len(message) == 0) or
        str(message).strip() == "{}"
    )
    
    if mensagem_vazia and req.respostaHSM and titulo_hsm != "nps_buddha":
        message = req.respostaHSM
        print(f"⚠️  Mensagem vazia detectada - usando respostaHSM como mensagem: {message}")
    
    print("=" * 80)
    print(f"📬 {nome_agente} - Nova mensagem")
    print(f"Conversation ID: {conversation_id}")
    print(f"Mensagem: {message}")
    print(f"Histórico: {len(history)} mensagens")
    if req.tituloHSM:
        print(f"tituloHSM: {req.tituloHSM}")
    if req.respostaHSM:
        print(f"respostaHSM: {req.respostaHSM}")
    print("=" * 80)
    
    # Executa o agente selecionado
    result = await agente_atual.run(
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
    
    print(f"✅ {nome_agente} - Resposta: {output_text}")
    print("=" * 80)

    # =========================================================================
    # LÓGICA ESPECÍFICA DO AGENTE NPS
    # =========================================================================
    if titulo_hsm == "nps_buddha" or titulo_hsm is None:
        # VERIFICAÇÃO: Se usuário não respondeu com nota válida, reenviar opções
        nota_prof_atual = context_updated.get("nota_profissional")
        nota_unid_atual = context_updated.get("nota_unidade")
        
        # Se ainda não tem nota profissional (primeira pergunta ou reenvio)
        if nota_prof_atual is None:
            print("⚠️  NOTA PROFISSIONAL NÃO VALIDADA - Retornando opções com mensagem do agente")
            print("=" * 80)
            
            # Retorna a mensagem do agente com botões
            opcoes_resposta = {
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
                "botao_profissional": True
            }
            
            print(f"📤 RETORNO: {json.dumps(opcoes_resposta, ensure_ascii=False, indent=2)}")
            print("=" * 80)
            return opcoes_resposta
        
        # Se tem nota profissional mas não tem nota unidade
        if nota_prof_atual is not None and nota_unid_atual is None and len(history) >= 6:
            print("⚠️  NOTA UNIDADE NÃO VALIDADA - Reenviando opções")
            print("=" * 80)
            return retornar_segunda_pergunta(output_text)
        
        # ETAPA 2: SEGUNDA PERGUNTA - OPÇÕES UNIDADE (NPS)
        # Após validar nota do profissional, a tool marca nota_unidade_ativa=True
        if context_updated.get("nota_unidade_ativa", False):
            return retornar_segunda_pergunta(output_text)
    
    # =========================================================================
    # DETECÇÃO DE FLAGS DOS NOVOS AGENTES
    # =========================================================================
    
    # Flag: botao_confirmacao (Confirmação - SIM/NÃO)
    if context_updated.get("botao_confirmacao"):
        return retornar_botoes_confirmacao(output_text)
    
    # Flag: botao_reagendar_cancelar (Confirmação - Reagendar/Cancelar)
    if context_updated.get("botao_reagendar_cancelar"):
        return retornar_botoes_reagendar_cancelar(output_text)
    
    # Flag: botao_confirmacao_no_show (No Show - SIM/NÃO)
    if context_updated.get("botao_confirmacao_no_show"):
        return retornar_botoes_no_show(output_text)
    
    # Flag: ir_para_reagendamento (Transbordo)
    if context_updated.get("ir_para_reagendamento"):
        print("🚩 FLAG DETECTADA: ir_para_reagendamento = TRUE")
        print(f"🗑️  Agendando deleção da sessão em background: {conversation_id}")
        background_tasks.add_task(delete_session, conversation_id)
        return {
            "response": output_text,
            "confirmou_agendamento": context_updated.get("confirmou_agendamento"),
            "ir_para_reagendamento": True
        }

    # Flag: ir_para_cancelamento (Transbordo)
    if context_updated.get("ir_para_cancelamento"):
        print("🚩 FLAG DETECTADA: ir_para_cancelamento = TRUE")
        print(f"🗑️  Agendando deleção da sessão em background: {conversation_id}")
        background_tasks.add_task(delete_session, conversation_id)
        return {
            "response": output_text,
            "confirmou_agendamento": context_updated.get("confirmou_agendamento"),
            "ir_para_cancelamento": True
        }

    # Flag: ir_para_reagendamento_no_show (Transbordo)
    if context_updated.get("ir_para_reagendamento_no_show"):
        print("🚩 FLAG DETECTADA: ir_para_reagendamento_no_show = TRUE")
        print(f"🗑️  Agendando deleção da sessão em background: {conversation_id}")
        background_tasks.add_task(delete_session, conversation_id)
        return {
            "response": output_text,
            "ir_para_reagendamento_no_show": True
        }
    
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
