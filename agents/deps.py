from dataclasses import dataclass
from typing import Optional

@dataclass
class MyDeps:
    session_id: str
    codigo_usuario: Optional[str] = None
    nome: Optional[str] = None
    nome_informado: Optional[str] = None  # Nome informado pelo usuário no início da conversa
    cpf: Optional[str] = None
    celular: Optional[str] = None
    email: Optional[str] = None
    dtNascimento: Optional[str] = None
    genero: Optional[str] = None

    # NOVOS CAMPOS PARA CONTROLE DE CADASTRO
    campos_faltantes: Optional[list[str]] = None
    cadastro_completo: Optional[bool] = None

    codigo_categoria: Optional[str] = None
    terapia: Optional[str] = None
    duracao: Optional[int] = None
    terapeuta: Optional[str] = None
    codigo_terapeuta: Optional[int] = None
    data: Optional[str] = None
    dia_semana: Optional[str] = None
    horario: Optional[str] = None
    codigo_servico: Optional[str] = None
    nome_servico: Optional[str] = None
    label_servico: Optional[str] = None
    valor_servico: Optional[str] = None
    observacao: Optional[str] = None
    terapeuta_recorrente: Optional[str] = None
    quantidade_atendimentos: Optional[int] = None
    
    # CONTATOS DA UNIDADE
    contato_unidade: str = "11 99999-9999"
    site_buddha: str = "https://buddhaspa.com.br/"
    site_buddha_renovar: str = "https://buddhaspa.com.br/renovacao/"
    
    # CONTROLE DE TENTATIVAS DE CPF PARA PACOTE
    tentativas_cpf_pacote: int = 0
    
    # TIPO DE BENEFÍCIO (voucher, pacote ou vale)
    tipo_beneficio: Optional[str] = None
    voucher: Optional[str] = None  # Código do voucher ou vale bem-estar
    
    # LISTA DE TERAPIAS DISPONÍVEIS (para pacotes)
    terapias_disponiveis: Optional[list] = None
    
    # CÓDIGO DO CLIENTE DO PACOTE (pode ser diferente do codigo_usuario)
    codigo_cliente_pacote: Optional[int] = None
    
    # DADOS DO PACOTE/PLANO
    cod_plano: Optional[str] = None  # Código do plano/pacote para desconto de saldo
    nome_plano: Optional[str] = None  # Nome do plano/pacote
    
    # DADOS DO VALE BEM-ESTAR
    valor_vale: Optional[str] = None  # Valor do vale (ex: "100,00")
    tipo_valor_vale: Optional[str] = None  # "Percentual(%)" ou "Real(R$)"
    valor_terapia: Optional[float] = None  # Valor da terapia escolhida
    
    # NAVEGAÇÃO ENTRE TERAPIAS (FLUXO 2)
    ultima_terapia_visualizada: Optional[str] = None  # Última terapia que o usuário viu explicação
    categoria_macro_escolhida: Optional[str] = None  # Categoria macro escolhida pelo usuário
    variacoes_terapia: Optional[list] = None  # Variações de duração da terapia escolhida
    
    # AGENDAMENTO
    data_agendamento: Optional[str] = None  # Data escolhida pelo usuário (DD/MM/AAAA)
    periodo: Optional[str] = None  # Período escolhido: manhã, tarde ou noite
    lista_terapeutas: Optional[list] = None  # Lista de terapeutas retornados pela API de listagem
    terapeuta_codProf: Optional[str] = None  # Código do terapeuta escolhido
    terapeuta_escolhido: Optional[str] = None  # Nome do terapeuta escolhido
    horarios_disponiveis: Optional[list] = None  # Lista de horários disponíveis do terapeuta
    horario_escolhido: Optional[str] = None  # Horário escolhido pelo usuário
    datas_alternativas: Optional[list] = None  # Próximas datas disponíveis do terapeuta
    terapeuta_alternativo_nome: Optional[str] = None  # Nome do terapeuta alternativo
    terapeuta_alternativo_cod: Optional[str] = None  # Código do terapeuta alternativo
    
    # SALA
    codSala: Optional[str] = None  # Código da sala escolhida para o agendamento
    nome_sala: Optional[str] = None  # Nome da sala escolhida
    
    # REAGENDAMENTO
    em_reagendamento: Optional[bool] = None  # Flag para indicar que está em processo de reagendamento
    cod_servico: Optional[str] = None  # Código do serviço capturado do agendamento cancelado
    
    # TRACKING DE NAVEGAÇÃO
    steps: Optional[list[str]] = None  # Histórico de steps percorridos pelo usuário
    
    # CAMPOS ESPECÍFICOS DO NPS
    nota_profissional: Optional[int] = None  # Nota de 1 a 5 para o profissional
    nota_unidade: Optional[int] = None  # Nota de 1 a 5 para a unidade
    feedback_texto: Optional[str] = None  # Feedback textual opcional
    profissional: Optional[str] = None  # Nome do profissional avaliado
    codigo_agendamento: Optional[str] = None  # Código do agendamento
    unidade_codigo: Optional[str] = None  # Código da unidade
    telefone: Optional[str] = None  # Telefone do cliente
    hsm_template_id: Optional[str] = None  # ID do template HSM usado
    hsm_metadata: Optional[dict] = None  # Metadados adicionais do HSM