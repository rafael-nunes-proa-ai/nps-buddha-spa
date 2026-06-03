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
    
    # FLAGS PARA SISTEMA EXTERNO (ATIVAR/DESATIVAR BOTÕES)
    botao_profissional: Optional[bool] = None  # Flag para ativar botões de avaliação do profissional
    botao_unidade: Optional[bool] = None  # Flag para ativar botões de avaliação da unidade
    
    # CONTROLE DE FINALIZAÇÃO
    mensagem_final_enviada: Optional[bool] = None  # Flag para indicar que mensagem final foi enviada
    finalizar_sessao: Optional[bool] = None  # Flag para React Flow encerrar conversa
    
    # METADADOS HSM
    hsm_template_id: Optional[str] = None
    hsm_metadata: Optional[dict] = None
    tituloHSM: Optional[str] = None  # Identificador do fluxo HSM
    respostaHSM: Optional[str] = None  # Resposta inicial do HSM
    
    # CONTROLE DE FLUXO - CONFIRMAÇÃO
    confirmou_agendamento: Optional[bool] = None  # True = confirmou, False = não confirmou
    botao_confirmacao: Optional[bool] = None  # Flag para exibir botões SIM/NÃO (confirmação)
    botao_reagendar_cancelar: Optional[bool] = None  # Flag para exibir botões Reagendar/Cancelar
    ir_para_reagendamento: Optional[bool] = None  # Flag para transbordo para reagendamento
    ir_para_cancelamento: Optional[bool] = None  # Flag para transbordo para cancelamento
    
    # CONTROLE DE FLUXO - NO SHOW
    botao_confirmacao_no_show: Optional[bool] = None  # Flag para exibir botões SIM/NÃO (no show)
    ir_para_reagendamento_no_show: Optional[bool] = None  # Flag para transbordo para reagendamento no show