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
    
    # Armazena no contexto e marca flag para exibir lista de avaliação da unidade
    update_context(conversation_id, {
        "nota_profissional": nota_extraida,
        "nota_unidade_ativa": True
    })
    
    print(f"✅ Nota profissional armazenada: {nota_extraida}")
    print(f"✅ Flag nota_unidade_ativa marcada como True")
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
    
    # Armazena no contexto e desliga TODAS as flags de opções
    # Para notas 3, 4 e 5, marca que mensagem final será enviada
    if nota_extraida >= 3:
        update_context(conversation_id, {
            "nota_unidade": nota_extraida,
            "nota_profissional_ativa": False,
            "nota_unidade_ativa": False,
            "mensagem_final_enviada": True  # Marca que mensagem final será enviada
        })
    else:
        # Para notas 1 e 2, ainda precisa coletar feedback
        update_context(conversation_id, {
            "nota_unidade": nota_extraida,
            "nota_profissional_ativa": False,
            "nota_unidade_ativa": False
        })
    
    print(f"✅ Nota unidade armazenada: {nota_extraida}")
    print(f"✅ Flags nota_profissional_ativa e nota_unidade_ativa desligadas (False)")
    if nota_extraida >= 3:
        print(f"✅ Flag mensagem_final_enviada marcada como True (nota {nota_extraida})")
    print("=" * 80)
    
    # Retorna instruções explícitas baseadas na nota
    if nota_extraida <= 2:
        return (
            f"NOTA_UNIDADE_VALIDA|{nota_extraida}\n"
            "PRÓXIMO PASSO: Peça feedback ao cliente com a mensagem:\n"
            '"Por favor, conte o que aconteceu para que possamos entender melhor a situação e buscar uma solução."\n'
            "Aguarde a resposta e use armazenar_feedback para salvar."
        )
    elif nota_extraida == 3:
        return (
            f"NOTA_UNIDADE_VALIDA|{nota_extraida}\n"
            "PRÓXIMO PASSO: NÃO peça feedback. Responda:\n"
            '"Agradecemos por compartilhar sua experiência.\n'
            "Suas respostas são muito importantes e nos ajudam a cuidar de cada detalhe com ainda mais atenção.\n\n"
            'Esperamos receber você novamente em breve.👋"'
        )
    else:  # 4 ou 5
        return (
            f"NOTA_UNIDADE_VALIDA|{nota_extraida}\n"
            "PRÓXIMO PASSO: NÃO peça feedback. Responda:\n"
            '"Ficamos muito felizes com isso!\n'
            "Sua experiência é muito especial para nós. Se puder, que tal compartilhar sua opinião deixando uma avaliação no Google?\n"
            "Ela nos ajuda a continuar cuidando de cada detalhe com carinho. https://g.page/r/CCFEE85I5qkEAE/review\n\n"
            'Será um prazer receber você novamente em breve. Até a próxima! 🥰"'
        )


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
    
    # Armazena no contexto e marca que mensagem final será enviada
    update_context(conversation_id, {
        "resposta_feedback_unidade": feedback,
        "mensagem_final_enviada": True  # Marca que após feedback, mensagem final será enviada
    })
    
    print(f"✅ Feedback armazenado")
    print(f"✅ Flag mensagem_final_enviada marcada como True (após feedback)")
    print("=" * 80)
    
    return "FEEDBACK_ARMAZENADO"


# ============================================================================
# TOOL 4 e 5: DESABILITADAS - Não salva mais em DB
# ============================================================================
# Removido: salvar_avaliacao_completa e encerrar_pesquisa


# ============================================================================
# TOOL 6: Gerar Lista Interativa WhatsApp
# ============================================================================

def gerar_lista_notas() -> str:
    """
    Gera a lista interativa de notas no formato WhatsApp.
    
    Returns:
        String formatada para lista interativa
    """
    return "Lista [[5|Excelente]][[4|Bom]][[3|Regular]][[2|Ruim]][[1|Péssimo]]"
