from dataclasses import dataclass
from typing import Optional

@dataclass
class MyDeps:
    """Dependências para o agente NPS - Pesquisa de Satisfação"""
    session_id: str
    
    # DADOS DO CLIENTE
    nome: Optional[str] = None
    telefone: Optional[str] = None
    
    # DADOS DO ATENDIMENTO
    profissional: Optional[str] = None
    codigo_agendamento: Optional[str] = None
    unidade_codigo: Optional[str] = None
    
    # AVALIAÇÕES NPS
    nota_profissional: Optional[int] = None
    nota_unidade: Optional[int] = None
    feedback_texto: Optional[str] = None
    resposta_feedback_unidade: Optional[str] = None  # Resposta do usuário sobre feedback
    
    # CONTROLE DE FLUXO (FLAGS PARA EXIBIR OPÇÕES)
    nota_profissional_ativa: Optional[bool] = None  # Flag para exibir opções de avaliação do profissional
    nota_unidade_ativa: Optional[bool] = None  # Flag para exibir opções de avaliação da unidade
    nps_unidade: Optional[bool] = None  # Flag legada (manter para compatibilidade)
    
    # CONTROLE DE FINALIZAÇÃO
    finalizar_sessao: Optional[bool] = None  # Flag para React Flow encerrar conversa
    
    # METADADOS HSM
    hsm_template_id: Optional[str] = None
    hsm_metadata: Optional[dict] = None