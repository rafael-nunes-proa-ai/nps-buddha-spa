"""
Tools para o Agente de Confirmação de Agendamento
"""
from pydantic_ai import RunContext
from agents.deps import MyDeps
from store.database import update_context


def ativar_botoes_reagendar_cancelar(ctx: RunContext[MyDeps]) -> str:
    """
    Ativa a flag para exibir botões Reagendar/Cancelar.
    
    Returns:
        Confirmação
    """
    conversation_id = ctx.deps.session_id
    
    print("=" * 80)
    print("🔍 TOOL: ativar_botoes_reagendar_cancelar")
    print(f"Conversation ID: {conversation_id}")
    print("=" * 80)
    
    print("🚩 Ativando flag botao_reagendar_cancelar")
    update_context(conversation_id, {"botao_reagendar_cancelar": True})
    
    print("✅ Flag ativada - botões serão exibidos")
    print("=" * 80)
    
    return "BOTOES_ATIVADOS"


def validar_confirmacao(ctx: RunContext[MyDeps], resposta: str) -> str:
    """
    Valida se a resposta do cliente é afirmativa, negativa ou inválida.
    
    Args:
        resposta: Resposta do cliente
        
    Returns:
        "AFIRMATIVA", "NEGATIVA" ou "INVALIDA"
    """
    conversation_id = ctx.deps.session_id
    
    print("=" * 80)
    print("🔍 TOOL: validar_confirmacao")
    print(f"Conversation ID: {conversation_id}")
    print(f"Resposta recebida: {resposta}")
    print("=" * 80)
    
    resposta_lower = resposta.lower().strip()
    
    # Respostas afirmativas
    afirmativas = ["sim", "s", "yes", "y", "confirmo", "confirmar", "ok", "pode ser", "claro", "com certeza"]
    
    # Respostas negativas
    negativas = ["não", "nao", "n", "no", "não confirmo", "nao confirmo", "cancelar", "desmarcar"]
    
    if any(palavra in resposta_lower for palavra in afirmativas):
        print("✅ Resposta AFIRMATIVA detectada")
        print("🚩 Marcando mensagem_final_enviada = True")
        update_context(conversation_id, {"mensagem_final_enviada": True})
        print("=" * 80)
        return "AFIRMATIVA"
    
    elif any(palavra in resposta_lower for palavra in negativas):
        print("✅ Resposta NEGATIVA detectada")
        print("=" * 80)
        return "NEGATIVA"
    
    else:
        print("⚠️ Resposta INVÁLIDA - não é clara")
        print("🚩 Ativando flag botao_confirmacao para exibir botões")
        
        # Ativa flag para exibir botões
        update_context(conversation_id, {"botao_confirmacao": True})
        
        print("=" * 80)
        return "INVALIDA"


def processar_escolha_reagendar_cancelar(ctx: RunContext[MyDeps], escolha: str) -> str:
    """
    Processa a escolha do cliente entre reagendar ou cancelar.
    
    Args:
        escolha: "Reagendar" ou "Cancelar"
        
    Returns:
        "REAGENDAR" ou "CANCELAR"
    """
    conversation_id = ctx.deps.session_id
    
    print("=" * 80)
    print("🔍 TOOL: processar_escolha_reagendar_cancelar")
    print(f"Conversation ID: {conversation_id}")
    print(f"Escolha recebida: {escolha}")
    print("=" * 80)
    
    escolha_lower = escolha.lower().strip()
    
    if "reagendar" in escolha_lower or "remarcar" in escolha_lower:
        print("✅ Cliente escolheu REAGENDAR")
        print("🚩 Ativando flag ir_para_reagendamento")
        print("🚫 Desativando flag botao_reagendar_cancelar")
        
        # Atualiza contexto: ativa transbordo e desativa botões
        update_context(conversation_id, {
            "ir_para_reagendamento": True,
            "botao_reagendar_cancelar": False
        })
        
        print("=" * 80)
        return "REAGENDAR"
    
    elif "cancelar" in escolha_lower or "desmarcar" in escolha_lower:
        print("✅ Cliente escolheu CANCELAR")
        print("🚩 Ativando flag ir_para_cancelamento")
        print("🚫 Desativando flag botao_reagendar_cancelar")
        
        # Atualiza contexto: ativa transbordo e desativa botões
        update_context(conversation_id, {
            "ir_para_cancelamento": True,
            "botao_reagendar_cancelar": False
        })
        
        print("=" * 80)
        return "CANCELAR"
    
    else:
        print("⚠️ Escolha não reconhecida")
        print("=" * 80)
        return "INVALIDA"
