"""
Tools para o Agente NPS
Ferramentas para processar avaliações de satisfação
"""

import os
import re
from datetime import datetime
from pydantic_ai import RunContext
from pydantic_ai.tools import Tool
from agents.deps import MyDeps
from store.database import update_context, delete_session, get_session
import json


# ============================================================================
# TOOL 1: Validar e Armazenar Nota do Profissional
# ============================================================================

@Tool
async def validar_nota_profissional(ctx: RunContext[MyDeps], nota: str) -> str:
    """
    Valida a nota dada ao profissional (1-5) e armazena no contexto.
    
    Args:
        nota: Nota de 1 a 5
    
    Returns:
        Mensagem de confirmação ou erro
    """
    conversation_id = ctx.deps.session_id
    
    print("=" * 80)
    print("🔍 TOOL: validar_nota_profissional")
    print(f"Conversation ID: {conversation_id}")
    print(f"Nota recebida: {nota}")
    print("=" * 80)
    
    # Extrai número da mensagem (aceita "5", "nota 5", "Excelente", etc)
    nota_extraida = None
    
    # Tenta extrair número diretamente
    numeros = re.findall(r'\b[1-5]\b', nota)
    if numeros:
        nota_extraida = int(numeros[0])
    
    if nota_extraida is None:
        return "❌ Não consegui identificar a nota. Por favor, escolha uma opção de 1 a 5."
    
    # Armazena no contexto
    update_context(conversation_id, {
        "nota_profissional": nota_extraida
    })
    
    print(f"✅ Nota profissional armazenada: {nota_extraida}")
    print("=" * 80)
    
    return f"NOTA_PROFISSIONAL_VALIDA|{nota_extraida}"


# ============================================================================
# TOOL 2: Validar e Armazenar Nota da Unidade
# ============================================================================

@Tool
async def validar_nota_unidade(ctx: RunContext[MyDeps], nota: str) -> str:
    """
    Valida a nota dada à unidade (1-5) e armazena no contexto.
    
    Args:
        nota: Nota de 1 a 5
    
    Returns:
        Mensagem de confirmação ou erro
    """
    conversation_id = ctx.deps.session_id
    
    print("=" * 80)
    print("🔍 TOOL: validar_nota_unidade")
    print(f"Conversation ID: {conversation_id}")
    print(f"Nota recebida: {nota}")
    print("=" * 80)
    
    # Extrai número da mensagem
    nota_extraida = None
    numeros = re.findall(r'\b[1-5]\b', nota)
    if numeros:
        nota_extraida = int(numeros[0])
    
    if nota_extraida is None:
        return "❌ Não consegui identificar a nota. Por favor, escolha uma opção de 1 a 5."
    
    # Armazena no contexto
    update_context(conversation_id, {
        "nota_unidade": nota_extraida
    })
    
    print(f"✅ Nota unidade armazenada: {nota_extraida}")
    print("=" * 80)
    
    return f"NOTA_UNIDADE_VALIDA|{nota_extraida}"


# ============================================================================
# TOOL 3: Armazenar Feedback Textual
# ============================================================================

@Tool
async def armazenar_feedback(ctx: RunContext[MyDeps], feedback: str) -> str:
    """
    Armazena o feedback textual do cliente.
    
    Args:
        feedback: Texto do feedback
    
    Returns:
        Confirmação
    """
    conversation_id = ctx.deps.session_id
    
    print("=" * 80)
    print("🔍 TOOL: armazenar_feedback")
    print(f"Conversation ID: {conversation_id}")
    print(f"Feedback: {feedback}")
    print("=" * 80)
    
    # Armazena no contexto
    update_context(conversation_id, {
        "resposta_feedback_unidade": feedback
    })
    
    print(f"✅ Feedback armazenado")
    print("=" * 80)
    
    return "FEEDBACK_ARMAZENADO"


# ============================================================================
# TOOL 4: Salvar Avaliação Completa no Banco
# ============================================================================

@Tool
async def salvar_avaliacao_completa(ctx: RunContext[MyDeps]) -> str:
    """
    Salva a avaliação completa no banco de dados (tabela avaliacoes_nps).
    
    Returns:
        Confirmação de salvamento
    """
    from store.database import salvar_avaliacao_nps
    
    conversation_id = ctx.deps.session_id
    
    print("=" * 80)
    print("🔍 TOOL: salvar_avaliacao_completa")
    print(f"Conversation ID: {conversation_id}")
    print("=" * 80)
    
    # Busca dados do contexto
    session = get_session(conversation_id)
    if not session:
        print("❌ Sessão não encontrada")
        return "ERRO_SESSAO"
    
    context = session[2] or {}
    if isinstance(context, str):
        try:
            context = json.loads(context) if context.strip() else {}
        except:
            context = {}
    
    # Extrai dados
    nota_profissional = context.get("nota_profissional")
    nota_unidade = context.get("nota_unidade")
    feedback = context.get("resposta_feedback_unidade", "")
    nome_cliente = context.get("nome", "")
    telefone = context.get("telefone", conversation_id)
    profissional = context.get("profissional", "")
    codigo_agendamento = context.get("codigo_agendamento", "")
    unidade_codigo = context.get("unidade_codigo", "1")
    hsm_template_id = context.get("hsm_template_id", "")
    hsm_metadata = context.get("hsm_metadata", {})
    
    print(f"Dados da avaliação:")
    print(f"  - Nota profissional: {nota_profissional}")
    print(f"  - Nota unidade: {nota_unidade}")
    print(f"  - Feedback: {feedback}")
    print(f"  - Cliente: {nome_cliente}")
    print(f"  - Telefone: {telefone}")
    print(f"  - Profissional: {profissional}")
    
    try:
        # Salva no banco de dados
        avaliacao_id = salvar_avaliacao_nps(
            session_id=conversation_id,
            telefone=telefone,
            nome_cliente=nome_cliente,
            profissional=profissional,
            codigo_agendamento=codigo_agendamento,
            unidade_codigo=unidade_codigo,
            nota_profissional=nota_profissional,
            nota_unidade=nota_unidade,
            feedback_texto=feedback if feedback else None,
            hsm_template_id=hsm_template_id if hsm_template_id else None,
            hsm_metadata=hsm_metadata if hsm_metadata else None
        )
        
        print(f"✅ Avaliação salva no banco! ID: {avaliacao_id}")
        print("=" * 80)
        
        return "AVALIACAO_SALVA"
        
    except Exception as e:
        print(f"❌ Erro ao salvar avaliação: {e}")
        print("=" * 80)
        return "ERRO_SALVAMENTO"


# ============================================================================
# TOOL 5: Encerrar Pesquisa
# ============================================================================

@Tool
async def encerrar_pesquisa(ctx: RunContext[MyDeps]) -> str:
    """
    Encerra a pesquisa NPS deletando a sessão.
    
    Returns:
        Confirmação
    """
    from store.database import get_session
    
    conversation_id = ctx.deps.session_id
    
    print("=" * 80)
    print("🔍 TOOL: encerrar_pesquisa")
    print(f"Conversation ID: {conversation_id}")
    print("=" * 80)
    
    # Verifica se sessão existe antes de deletar
    session_antes = get_session(conversation_id)
    if session_antes:
        print(f"📊 Sessão encontrada no banco antes de deletar")
    else:
        print("⚠️  Sessão não encontrada no banco")
    
    # Deleta a sessão
    print("🗑️  Deletando sessão do banco de dados...")
    delete_session(conversation_id)
    
    # Verifica se sessão foi realmente deletada
    session_depois = get_session(conversation_id)
    if session_depois is None:
        print("✅ CONFIRMADO: Sessão deletada com sucesso do banco de dados")
    else:
        print("❌ ERRO: Sessão ainda existe no banco após delete_session()")
    
    print("✅ Pesquisa encerrada")
    print("=" * 80)
    
    return "PESQUISA_ENCERRADA"


# ============================================================================
# TOOL 6: Gerar Opções de Notas no Formato Canônico
# ============================================================================

@Tool
async def gerar_opcoes_notas(ctx: RunContext[MyDeps], title: str) -> dict:
    """
    Gera opções de notas (1-5) no formato canônico para React Flow.
    
    Args:
        title: Título/pergunta a ser exibida acima das opções
    
    Returns:
        Dict com estrutura output.generic
    """
    print("=" * 80)
    print("🔍 TOOL: gerar_opcoes_notas")
    print(f"Title: {title}")
    print("=" * 80)
    
    # Formato AWS Broker com output (sem description, labels simples)
    output = {
        "output": {
            "generic": [
                {
                    "response_type": "option",
                    "title": title,
                    "options": [
                        {"label": "5", "value": {"input": {"text": "5"}}},
                        {"label": "4", "value": {"input": {"text": "4"}}},
                        {"label": "3", "value": {"input": {"text": "3"}}},
                        {"label": "2", "value": {"input": {"text": "2"}}},
                        {"label": "1", "value": {"input": {"text": "1"}}}
                    ]
                }
            ]
        }
    }
    
    print(f"✅ Objeto gerado: {str(output)[:100]}...")
    print("=" * 80)
    
    return output
