"""
Tools para o Agente de No Show sem Consumo de Voucher
"""
from pydantic_ai import RunContext
from agents.deps import MyDeps
from store.database import update_context


def validar_resposta_no_show(ctx: RunContext[MyDeps], resposta: str) -> str:
    """
    Valida se a resposta do cliente sobre reagendamento é afirmativa, negativa ou inválida.
    
    Args:
        resposta: Resposta do cliente
        
    Returns:
        "AFIRMATIVA", "NEGATIVA" ou "INVALIDA"
    """
    conversation_id = ctx.deps.session_id
    
    print("=" * 80)
    print("🔍 TOOL: validar_resposta_no_show")
    print(f"Conversation ID: {conversation_id}")
    print(f"Resposta recebida: {resposta}")
    print("=" * 80)
    
    resposta_lower = resposta.lower().strip()
    
    # Respostas afirmativas
    afirmativas = ["sim", "s", "yes", "y", "quero", "vamos", "ok", "pode ser", "claro", "com certeza", "reagendar"]
    
    # Respostas negativas
    negativas = ["não", "nao", "n", "no", "não quero", "nao quero", "deixa pra lá", "deixa"]
    
    if any(palavra in resposta_lower for palavra in afirmativas):
        print("✅ Resposta AFIRMATIVA detectada")
        print("🚩 Ativando flag ir_para_reagendamento_no_show")
        
        # Atualiza contexto com flag de transbordo
        update_context(conversation_id, {"ir_para_reagendamento_no_show": True})
        
        print("=" * 80)
        return "AFIRMATIVA"
    
    elif any(palavra in resposta_lower for palavra in negativas):
        print("✅ Resposta NEGATIVA detectada")
        print("🚩 Marcando mensagem_final_enviada = True")
        update_context(conversation_id, {"mensagem_final_enviada": True})
        print("=" * 80)
        return "NEGATIVA"
    
    else:
        print("⚠️ Resposta INVÁLIDA - não é clara")
        print("🚩 Ativando flag botao_confirmacao_no_show para exibir botões")
        
        # Ativa flag para exibir botões
        update_context(conversation_id, {"botao_confirmacao_no_show": True})
        
        print("=" * 80)
        return "INVALIDA"
