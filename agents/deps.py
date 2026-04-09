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
    
    # CONTROLE DE FLUXO
    nps_unidade: Optional[bool] = None  # Flag para exibir lista de avaliação da unidade
    
    # METADADOS HSM
    hsm_template_id: Optional[str] = None
    hsm_metadata: Optional[dict] = None