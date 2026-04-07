"""
Tools para o fluxo novo (agent_new.py)
Apenas tools necessárias, sem lógica do fluxo antigo
"""

import os
import requests
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from pydantic_ai import RunContext
from pydantic_ai.tools import Tool
from agents.deps import MyDeps
from store.database import update_context, update_current_agent, get_session
import utils
import json
import re

TZ_BR = ZoneInfo("America/Sao_Paulo")

# Campos obrigatórios para cadastro completo
CAMPOS_CADASTRO_OBRIGATORIOS = [
    "nome",
    "cpf",
    "celular",
    "email",
    "dtNascimento",
    "genero"
]

# ============================================================================
# FUNÇÃO AUXILIAR: Validação de Horários com Duração + Intervalo
# ============================================================================

def validar_horarios_com_duracao(horarios_disponiveis: list, duracao_terapia: int, intervalo_minutos: int = 10) -> list:
    """
    Valida horários considerando duração da terapia + intervalo obrigatório.
    
    Lógica:
    - Para cada horário disponível, verifica se há tempo livre suficiente
    - Tempo necessário = duracao_terapia + intervalo_minutos
    - Valida se não há outro horário ocupado dentro desse período
    
    Args:
        horarios_disponiveis: Lista de horários disponíveis (formato "HH:MM")
        duracao_terapia: Duração da terapia em minutos (ex: 60)
        intervalo_minutos: Intervalo obrigatório após terapia (padrão: 10)
    
    Returns:
        Lista de horários válidos que comportam terapia + intervalo
    
    Exemplo:
        Terapia 60min com intervalo 10min = 70min total:
        - 13:00 → precisa estar livre até 14:10
        - Se o próximo horário ocupado for 14:15, então 13:00 é válido ✅
    """
    if not horarios_disponiveis or not duracao_terapia:
        return []
    
    # Converte horários para datetime para facilitar cálculos
    try:
        horarios_dt = []
        for h in horarios_disponiveis:
            hora, minuto = h.split(':')
            dt = datetime.strptime(h, "%H:%M")
            horarios_dt.append((h, dt))
        
        # Ordena por horário
        horarios_dt.sort(key=lambda x: x[1])
        
        # Tempo total necessário
        tempo_total_necessario = duracao_terapia + intervalo_minutos
        
        print(f"  🔍 VALIDAÇÃO DE HORÁRIOS:")
        print(f"     Duração terapia: {duracao_terapia} min")
        print(f"     Intervalo: {intervalo_minutos} min")
        print(f"     Total necessário: {tempo_total_necessario} min")
        
        horarios_validos = []
        
        for i, (horario_str, horario_dt) in enumerate(horarios_dt):
            horario_final_necessario = horario_dt + timedelta(minutes=tempo_total_necessario)
            
            # Verifica se há blocos consecutivos suficientes
            # Os horários da API já são LIVRES, então preciso verificar se há
            # horários consecutivos suficientes para cobrir duração + intervalo
            blocos_necessarios = (tempo_total_necessario + intervalo_minutos - 1) // intervalo_minutos
            blocos_encontrados = 1
            horario_atual = horario_dt
            
            # Conta quantos blocos consecutivos existem
            for j in range(i + 1, len(horarios_dt)):
                proximo_horario = horarios_dt[j][1]
                diferenca = (proximo_horario - horario_atual).total_seconds() / 60
                
                # Se o próximo está no intervalo correto, é consecutivo
                if diferenca == intervalo_minutos:
                    blocos_encontrados += 1
                    horario_atual = proximo_horario
                    
                    # Se já temos blocos suficientes, este horário inicial é válido
                    if blocos_encontrados >= blocos_necessarios:
                        horarios_validos.append(horario_str)
                        print(f"     ✅ {horario_str} → VÁLIDO ({blocos_encontrados} blocos consecutivos, fim em {horario_final_necessario.strftime('%H:%M')})")
                        break
                else:
                    # Encontrou um buraco, não há blocos suficientes
                    print(f"     ❌ {horario_str} → INVÁLIDO (apenas {blocos_encontrados}/{blocos_necessarios} blocos, buraco em {proximo_horario.strftime('%H:%M')})")
                    break
            else:
                # Chegou ao fim sem break - verifica se tem blocos suficientes
                if blocos_encontrados >= blocos_necessarios:
                    horarios_validos.append(horario_str)
                    print(f"     ✅ {horario_str} → VÁLIDO ({blocos_encontrados} blocos até o fim)")
                else:
                    print(f"     ❌ {horario_str} → INVÁLIDO (apenas {blocos_encontrados}/{blocos_necessarios} blocos até o fim)")
        
        print(f"  📊 Resultado: {len(horarios_validos)}/{len(horarios_disponiveis)} horários válidos")
        return horarios_validos
        
    except Exception as e:
        print(f"  ❌ Erro ao validar horários: {e}")
        return horarios_disponiveis  # Em caso de erro, retorna todos

# ============================================================================
# FUNÇÕES AUXILIARES
# ============================================================================

def _normalizar_cpf(cpf: str | None) -> str:
    """Remove pontos, traços e espaços do CPF."""
    if not cpf:
        return ""
    return cpf.replace(".", "").replace("-", "").replace(" ", "").strip()

def _normalizar_celular(celular: str | None) -> str:
    """Remove parênteses, traços, espaços do celular."""
    if not celular:
        return ""
    return celular.replace("(", "").replace(")", "").replace("-", "").replace(" ", "").strip()

def _somente_numeros(texto: str | None) -> str:
    """Remove todos os caracteres não numéricos de um texto."""
    if not texto:
        return ""
    return ''.join(filter(str.isdigit, texto))

def _valor_preenchido(valor) -> bool:
    """Verifica se um valor está realmente preenchido (não é None, vazio ou placeholder)."""
    if valor is None:
        return False
    
    valor_str = str(valor).strip().lower()
    
    if not valor_str:
        return False
    
    placeholders = {
        "none",
        "null",
        "não informado",
        "nao informado",
        "000.000.000-00",
        "(00) 00000-0000",
        "naoinformado@buddha.com",
        "0000-00-00",  # Data vazia da Belle
        "00/00/0000",  # Data vazia alternativa
    }
    
    return valor_str not in placeholders

def _normalizar_cliente_belle(data: dict, celular_consultado: str = None) -> dict | None:
    """Normaliza os dados do cliente retornados pela API Belle."""
    if not data or not isinstance(data, dict):
        return None
    
    codigo = data.get("codigo")
    if not codigo:
        return None
    
    cpf_bruto = data.get("cpf", "")
    celular_bruto = data.get("celular", "")
    
    # Se não tiver celular na resposta, usa o celular consultado
    if not celular_bruto and celular_consultado:
        celular_bruto = celular_consultado
    
    return {
        "codigo_usuario": codigo,
        "nome": data.get("nome", "").strip(),
        "cpf": _normalizar_cpf(cpf_bruto),
        "celular": _normalizar_celular(celular_bruto),
        "email": data.get("email", "").strip(),
        "dtNascimento": data.get("dtNascimento", ""),
        "genero": data.get("sexo", "")
    }

# ============================================================================
# FUNÇÕES AUXILIARES: Validação de Salas
# ============================================================================

def _buscar_disponibilidade_salas(data_agendamento: str, periodo: str, codigo_servico: str) -> dict:
    """
    Busca disponibilidade de salas (tpAgd=s) para uma data/período/serviço.
    
    Args:
        data_agendamento: Data no formato DD/MM/AAAA
        periodo: Período (manha, tarde, noite, todos)
        codigo_servico: Código do serviço
    
    Returns:
        dict: {
            'codSala': {
                'nome': 'Nome da Sala',
                'horarios': ['10:00', '10:10', ...],
                'tempo_intervalo': '10'
            },
            ...
        }
    """
    url = f'https://app.bellesoftware.com.br/api/release/controller/IntegracaoExterna/v1.0/agenda/disponibilidade?codEstab=1&dtAgenda={data_agendamento}&periodo={periodo}&tpAgd=s&servicos={codigo_servico}'
    
    headers = {
        'Authorization': os.getenv("LABELLE_TOKEN")
    }
    
    try:
        print(f"\n🏢 BUSCANDO DISPONIBILIDADE DE SALAS:")
        print(f"   URL: {url}")
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        
        agendas = response.json()
        print(f"   📊 Total de agendas retornadas: {len(agendas)}")
        
        salas_disponiveis = {}
        
        for agenda in agendas:
            data_agenda = agenda.get('data', '')
            
            # FILTRO CRÍTICO: Apenas processa a agenda da data escolhida
            if data_agenda != data_agendamento:
                continue
            
            horarios = agenda.get("horarios", [])
            print(f"   ✅ Data correta! Total de salas nesta agenda: {len(horarios)}")
            
            for sala in horarios:
                # IMPORTANTE: API retorna código da sala como "codProf"
                cod_sala = str(sala.get("codProf", "")).strip()
                nome_sala = sala.get("nome", "")
                tempo_intervalo = sala.get("tempo_intervalo", "10")  # Captura intervalo da API
                horarios_sala = sala.get("horarios", [])
                
                # Extrai lista de horários
                lista_horarios = []
                if isinstance(horarios_sala, list):
                    for h in horarios_sala:
                        if isinstance(h, dict):
                            hora = h.get("horario", h.get("hora", ""))
                        else:
                            hora = str(h)
                        
                        if hora:
                            lista_horarios.append(hora)
                
                if cod_sala and lista_horarios:
                    salas_disponiveis[cod_sala] = {
                        'nome': nome_sala,
                        'horarios': lista_horarios,
                        'tempo_intervalo': tempo_intervalo
                    }
                    print(f"   🏢 Sala: {nome_sala} (cod: {cod_sala})")
                    print(f"      Intervalo: {tempo_intervalo} min")
                    print(f"      Horários: {len(lista_horarios)}")
            
            break  # Encontrou a data, não precisa continuar
        
        print(f"   📊 Total de salas disponíveis: {len(salas_disponiveis)}")
        return salas_disponiveis
        
    except Exception as e:
        print(f"   ❌ Erro ao buscar salas: {e}")
        return {}


def _cruzar_horarios_terapeuta_e_sala(
    horarios_terapeuta: list,
    intervalo_terapeuta: int,
    salas_disponiveis: dict,
    duracao_terapia: int
) -> tuple:
    """
    Cruza horários do terapeuta com horários das salas.
    Retorna apenas horários que têm blocos consecutivos suficientes em AMBOS.
    
    Args:
        horarios_terapeuta: Lista de horários do terapeuta
        intervalo_terapeuta: Intervalo do terapeuta em minutos
        salas_disponiveis: Dict com salas e seus horários
        duracao_terapia: Duração da terapia em minutos
    
    Returns:
        tuple: (horarios_validos, codSala_escolhida, nome_sala, intervalo_sala)
    """
    print(f"\n🔄 CRUZANDO HORÁRIOS TERAPEUTA X SALAS:")
    print(f"   Horários terapeuta: {len(horarios_terapeuta)}")
    print(f"   Intervalo terapeuta: {intervalo_terapeuta} min")
    print(f"   Salas disponíveis: {len(salas_disponiveis)}")
    print(f"   Duração terapia: {duracao_terapia} min")
    
    if not salas_disponiveis:
        print(f"   ❌ Nenhuma sala disponível")
        return ([], None, None, None)
    
    melhor_resultado = {
        'horarios': [],
        'codSala': None,
        'nome_sala': None,
        'intervalo_sala': None
    }
    
    # Tenta cada sala
    for cod_sala, dados_sala in salas_disponiveis.items():
        horarios_sala = dados_sala['horarios']
        nome_sala = dados_sala['nome']
        intervalo_sala = int(dados_sala['tempo_intervalo'])
        
        print(f"\n   🏢 Testando sala: {nome_sala} (cod: {cod_sala})")
        print(f"      Intervalo sala: {intervalo_sala} min")
        print(f"      Horários sala: {len(horarios_sala)}")
        
        # Valida horários da sala com sua duração + intervalo
        horarios_sala_validos = validar_horarios_com_duracao(
            horarios_disponiveis=horarios_sala,
            duracao_terapia=duracao_terapia,
            intervalo_minutos=intervalo_sala
        )
        
        print(f"      Horários sala válidos: {len(horarios_sala_validos)}")
        
        # Valida horários do terapeuta com sua duração + intervalo
        horarios_terapeuta_validos = validar_horarios_com_duracao(
            horarios_disponiveis=horarios_terapeuta,
            duracao_terapia=duracao_terapia,
            intervalo_minutos=intervalo_terapeuta
        )
        
        print(f"      Horários terapeuta válidos: {len(horarios_terapeuta_validos)}")
        
        # Encontra interseção (horários que estão em AMBOS)
        horarios_comuns = list(set(horarios_terapeuta_validos) & set(horarios_sala_validos))
        horarios_comuns.sort()
        
        print(f"      ✅ Horários em comum: {len(horarios_comuns)}")
        
        if horarios_comuns:
            # Se esta sala tem mais horários que a melhor até agora, usa ela
            if len(horarios_comuns) > len(melhor_resultado['horarios']):
                melhor_resultado = {
                    'horarios': horarios_comuns,
                    'codSala': cod_sala,
                    'nome_sala': nome_sala,
                    'intervalo_sala': intervalo_sala
                }
                print(f"      🏆 Melhor sala até agora: {len(horarios_comuns)} horários")
    
    if melhor_resultado['horarios']:
        print(f"\n   ✅ SALA ESCOLHIDA: {melhor_resultado['nome_sala']}")
        print(f"      Código: {melhor_resultado['codSala']}")
        print(f"      Horários válidos: {len(melhor_resultado['horarios'])}")
        print(f"      Intervalo: {melhor_resultado['intervalo_sala']} min")
    else:
        print(f"\n   ❌ Nenhuma sala com horários compatíveis")
    
    return (
        melhor_resultado['horarios'],
        melhor_resultado['codSala'],
        melhor_resultado['nome_sala'],
        melhor_resultado['intervalo_sala']
    )

# ============================================================================
# FUNÇÕES AUXILIARES: Cadastro
# ============================================================================

def verificar_campos_faltantes_cadastro(dados_cliente: dict) -> dict:
    """Verifica quais campos obrigatórios estão faltando no cadastro."""
    campos_faltantes = []
    campos_preenchidos = []
    
    for campo in CAMPOS_CADASTRO_OBRIGATORIOS:
        valor = dados_cliente.get(campo)
        if _valor_preenchido(valor):
            campos_preenchidos.append(campo)
        else:
            campos_faltantes.append(campo)
    
    return {
        "dados_cliente": dados_cliente,
        "campos_faltantes": campos_faltantes,
        "campos_preenchidos": campos_preenchidos,
        "cadastro_completo": len(campos_faltantes) == 0
    }

# ============================================================================
# TOOLS - VOUCHER/VALE/PACOTE
# ============================================================================

@Tool
def validar_voucher_ou_vale(ctx: RunContext[MyDeps], codigo_voucher: str, data_agendamento: str) -> str:
    """
    Valida um voucher ou vale bem-estar.

    Nova regra:
    - item preenchido -> voucher
    - item vazio -> vale bem-estar
    """
    conversation_id = ctx.deps.session_id
    print("=" * 80)
    print("DEBUG VALIDAR_VOUCHER_OU_VALE - INÍCIO")
    print(f"Conversation ID: {conversation_id}")
    print(f"Código voucher: {codigo_voucher}")
    print(f"Data agendamento recebida: {data_agendamento}")
    print(f"Tipo da data: {type(data_agendamento)}")
    print("=" * 80)

    url = f'https://app.bellesoftware.com.br/api/release/controller/IntegracaoExterna/v1.0/voucher/unico?codVoucher={codigo_voucher}'
    headers = {
        'Authorization': os.getenv("LABELLE_TOKEN")
    }

    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        data = response.json()

        print(f"Resultado da validação API: {data}")

        if not isinstance(data, dict):
            return "❌ Erro ao validar código."

        status = data.get("status", "").lower()

        # Puxa o tipo e item
        tipo_api = data.get("tipo", "")
        item = data.get("item")

        # REGRA: tipo="Serviços" ou "Servicos" → voucher (terapia predefinida)
        #        tipo="Geral" → vale bem-estar (valor para gastar)
        # Normaliza removendo acentos para comparação
        import unicodedata
        tipo_normalizado = unicodedata.normalize('NFD', tipo_api).encode('ascii', 'ignore').decode('utf-8').lower()
        is_voucher = tipo_normalizado == "servicos"
        tipo_label = "voucher" if is_voucher else "vale bem-estar"
        
        print(f"DEBUG - Tipo API: {tipo_api}")
        print(f"DEBUG - Tipo normalizado: {tipo_normalizado}")
        print(f"DEBUG - Is voucher: {is_voucher}")
        print(f"DEBUG - Tipo label: {tipo_label}")

        # Validação de status
        # ⚠️ Permite "voucher expirado" passar para ser tratado pela lógica de data vencida
        status_invalidos = ["cancelado", "utilizado", "bloqueado"]
        if any(s in status for s in status_invalidos):
            return f"❌ {tipo_label.title()} não pode ser utilizado. Status: {data.get('status')}"

        # Validação de data
        vencimento_fim = data.get("vencimentoFim")
        if not vencimento_fim:
            return f"⚠️ {tipo_label.title()} sem data de vencimento."

        print(f"DEBUG - Vencimento fim (API): {vencimento_fim}")
        print(f"DEBUG - Data agendamento (param): {data_agendamento}")
        
        try:
            dt_vencimento_fim = datetime.strptime(vencimento_fim, "%d/%m/%Y").date()
            print(f"DEBUG - dt_vencimento_fim parseado: {dt_vencimento_fim}")
        except Exception as e:
            print(f"ERRO ao parsear vencimento_fim: {e}")
            return f"❌ Erro ao processar data de vencimento: {vencimento_fim}"
        
        try:
            dt_agendamento = datetime.strptime(data_agendamento, "%d/%m/%Y").date()
            print(f"DEBUG - dt_agendamento parseado: {dt_agendamento}")
        except Exception as e:
            print(f"ERRO ao parsear data_agendamento: {e}")
            return f"❌ Erro ao processar data de agendamento: {data_agendamento}"

        # Dados comuns
        valor = data.get("valor", "0,00")
        tipo_valor = data.get("tipoValor", "")
        validade = f"{data.get('vencimentoIni')} até {vencimento_fim}"
        msg = data.get("msg", "")

        # Verifica se está vencido
        voucher_vencido = dt_agendamento > dt_vencimento_fim
        print(f"DEBUG - Voucher vencido? {voucher_vencido} (agendamento: {dt_agendamento} > vencimento: {dt_vencimento_fim})")
        print("=" * 80)

        # 🔥 Diferença principal (baseada no item)
        if is_voucher:
            terapia = item.get("nome", "Desconhecido")
            # API retorna 'codigo' dentro do item para vouchers
            codigo_servico = item.get("codigo", "") if item else ""

            # 🔥 SEMPRE armazena tipo_beneficio, terapia, codigo_servico E voucher (válido OU vencido)
            update_context(conversation_id, {
                "tipo_beneficio": "voucher",
                "terapia": terapia,
                "codigo_servico": codigo_servico,
                "voucher": codigo_voucher  # 🔥 Armazena código do voucher para observação
            })
            print(f"DEBUG - Contexto atualizado: tipo_beneficio=voucher, terapia={terapia}, codigo_servico={codigo_servico}, voucher={codigo_voucher}")
            
            # Atualiza ctx.deps para refletir as mudanças
            ctx.deps.tipo_beneficio = "voucher"
            ctx.deps.terapia = terapia
            print(f"DEBUG - ctx.deps atualizado: tipo_beneficio={ctx.deps.tipo_beneficio}, terapia={ctx.deps.terapia}")

            # VOUCHER VENCIDO - Mensagem especial
            if voucher_vencido:
                return (
                    f"⚠️ <strong>Este voucher está fora do prazo de validade.</strong> 🤔\n\n"
                    f"<strong>Terapia do voucher:</strong> {terapia}\n"
                    f"<strong>Validade:</strong> {validade}\n\n"
                    f"Se você o adquiriu pelo site, será necessário revalidá-lo no site para utilizá-lo.\n"
                    f"Se você o adquiriu na unidade, será necessário realizar o pagamento da diferença diretamente na unidade no dia do atendimento.\n\n"
                    f"Você pode continuar com o agendamento, mas a utilização do voucher ficará condicionada a essa regularização.\n\n"
                    f"<strong>Deseja continuar com o agendamento mesmo assim?</strong>"
                )

            # VOUCHER VÁLIDO - Retorna mensagem de sucesso
            
            return (
                f"✅ <strong>Voucher válido!</strong>\n"
                f"<strong>Terapia:</strong> {terapia}\n"
                f"<strong>Valor:</strong> {valor} {tipo_valor}\n"
                f"<strong>Validade:</strong> {validade}\n"
                f"Mensagem: {msg}\n\n"
                f"Podemos continuar com o seu agendamento?"
            )

        else:
            # 🔥 SEMPRE armazena tipo_beneficio, valor_vale, tipo_valor_vale E voucher (válido OU vencido)
            update_context(conversation_id, {
                "tipo_beneficio": "vale",
                "valor_vale": valor,  # Armazena valor para validação posterior
                "tipo_valor_vale": tipo_valor,  # "Percentual(%)" ou "Real(R$)"
                "voucher": codigo_voucher  # 🔥 Armazena código do vale para observação
            })
            print(f"DEBUG - Contexto atualizado: tipo_beneficio=vale, valor_vale={valor}, tipo_valor_vale={tipo_valor}, voucher={codigo_voucher}")
            
            # Atualiza ctx.deps para refletir as mudanças
            ctx.deps.tipo_beneficio = "vale"
            print(f"DEBUG - ctx.deps atualizado: tipo_beneficio={ctx.deps.tipo_beneficio}")
            
            # VALE BEM-ESTAR VENCIDO
            if voucher_vencido:
                return (
                    f"⚠️ <strong>Este vale está fora do prazo de validade.</strong> 🤔\n\n"
                    f"<strong>Valor disponível:</strong> {valor} {tipo_valor}\n"
                    f"<strong>Validade:</strong> {validade}\n\n"
                    f"Para utilizá-lo, será necessário o pagamento de uma diferença diretamente na unidade no dia do atendimento.\n\n"
                    f"<strong>Deseja continuar com o agendamento mesmo assim?</strong>"
                )

            # VALE BEM-ESTAR VÁLIDO
            
            return (
                f"✅ <strong>Vale bem-estar válido!</strong>\n"
                f"<strong>Valor disponível:</strong> {valor} {tipo_valor}\n"
                f"<strong>Validade:</strong> {validade}\n"
                f"Mensagem: {msg}\n\n"
                f"Podemos continuar com o seu agendamento?"
            )

    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 404:
            return "❌ Código não encontrado. Por favor, verifique e tente novamente."
        return f"❌ Erro ao validar: {str(e)}"
    except Exception as e:
        print(f"ERRO INESPERADO: {e}")
        import traceback
        traceback.print_exc()
        return f"❌ Erro inesperado: {str(e)}"

@Tool
def consultar_pacotes(ctx: RunContext[MyDeps], cpf: str) -> str:
    """Consulta pacotes disponíveis para um CPF.
    
    Fluxo:
    1. Busca cliente por CPF usando cliente/listar
    2. Pega o codigo (ID) do cliente
    3. Busca planos usando cliente/planos?codCliente={id}
    """
    conversation_id = ctx.deps.session_id
    
    session = get_session(conversation_id)
    context_atual = session[2] or {}
    
    if isinstance(context_atual, str):
        try:
            context_atual = json.loads(context_atual) if context_atual.strip() else {}
        except:
            context_atual = {}
    
    tentativas_cpf = context_atual.get("tentativas_cpf_pacote", 0)
    
    # Normaliza CPF (remove pontos, traços, etc)
    cpf_numeros = ''.join(filter(str.isdigit, cpf))
    
    print("=" * 80)
    print("DEBUG CONSULTAR_PACOTES - INÍCIO")
    print(f"CPF recebido: {cpf}")
    print(f"CPF normalizado: {cpf_numeros}")
    print("=" * 80)
    
    headers = {'Authorization': os.getenv("LABELLE_TOKEN")}
    
    try:
        # ETAPA 1: Buscar cliente por CPF
        url_cliente = f'https://app.bellesoftware.com.br/api/release/controller/IntegracaoExterna/v1.0/cliente/listar?cpf={cpf_numeros}&id=&codEstab=1&email=&celular='
        print(f"URL cliente: {url_cliente}")
        
        response = requests.get(url_cliente, headers=headers)
        print(f"Status cliente: {response.status_code}")
        response.raise_for_status()
        data_cliente = response.json()
        print(f"Resposta cliente (tipo): {type(data_cliente)}")
        print(f"Resposta cliente: {data_cliente}")
        
        # Verifica se encontrou cliente
        if not data_cliente:
            tentativas_cpf += 1
            update_context(conversation_id, {"tentativas_cpf_pacote": tentativas_cpf})
            
            if tentativas_cpf >= 2:
                update_context(conversation_id, {"tentativas_cpf_pacote": 0})
                return """❌ CPF não encontrado novamente.

Infelizmente não conseguimos localizar pacotes ativos para este CPF.

Por favor, entre em contato com a nossa unidade para mais informações:
📞 (11) 3796-7799
📱 WhatsApp: (11) 97348-5060
🌐 https://buddhaspa.com.br/

Até mais! 👋"""
            
            return "❌ CPF não encontrado. Deseja tentar novamente?"
        
        # Se for lista, pega primeiro item
        if isinstance(data_cliente, list):
            if len(data_cliente) == 0:
                tentativas_cpf += 1
                update_context(conversation_id, {"tentativas_cpf_pacote": tentativas_cpf})
                
                if tentativas_cpf >= 2:
                    update_context(conversation_id, {"tentativas_cpf_pacote": 0})
                    return """❌ CPF não encontrado novamente.

Infelizmente não conseguimos localizar pacotes ativos para este CPF.

Por favor, entre em contato com a nossa unidade para mais informações:
📞 (11) 3796-7799
📱 WhatsApp: (11) 97348-5060
🌐 https://buddhaspa.com.br/

Até mais! 👋"""
                
                return "❌ CPF não encontrado. Deseja tentar novamente?"
            cliente = data_cliente[0]
        else:
            cliente = data_cliente
        
        print(f"Cliente encontrado: {cliente}")
        
        # Pega o código (ID) do cliente
        codigo_cliente = cliente.get("codigo")
        print(f"Código do cliente: {codigo_cliente}")
        
        if not codigo_cliente:
            tentativas_cpf += 1
            update_context(conversation_id, {"tentativas_cpf_pacote": tentativas_cpf})
            
            if tentativas_cpf >= 2:
                update_context(conversation_id, {"tentativas_cpf_pacote": 0})
                return """❌ Não foi possível identificar seu cadastro novamente.

Por favor, entre em contato com a nossa unidade:
📞 (11) 3796-7799
📱 WhatsApp: (11) 97348-5060
🌐 https://buddhaspa.com.br/

Até mais! 👋"""
            
            return "❌ Não foi possível identificar seu cadastro. Deseja tentar novamente?"
        
        # ETAPA 2: Buscar planos do cliente
        url_planos = f'https://app.bellesoftware.com.br/api/release/controller/IntegracaoExterna/v1.0/cliente/planos?codCliente={codigo_cliente}&codEstab=1'
        print(f"URL planos: {url_planos}")
        
        response_planos = requests.get(url_planos, headers=headers)
        print(f"Status planos: {response_planos.status_code}")
        response_planos.raise_for_status()
        planos = response_planos.json()
        print(f"Planos encontrados: {planos}")
        print("=" * 80)
        
        if not planos or len(planos) == 0:
            tentativas_cpf += 1
            update_context(conversation_id, {"tentativas_cpf_pacote": tentativas_cpf})
            
            if tentativas_cpf >= 2:
                update_context(conversation_id, {"tentativas_cpf_pacote": 0})
                return """❌ Você não possui pacotes cadastrados.

Por favor, entre em contato com a nossa unidade para mais informações:
📞 (11) 3796-7799
📱 WhatsApp: (11) 97348-5060
🌐 https://buddhaspa.com.br/

Até mais! 👋"""
            
            return "❌ Você não possui pacotes cadastrados. Deseja tentar com outro CPF?"
        
        # SUCESSO - Atualiza TODOS os dados do contexto com os dados do cliente do pacote
        # A partir daqui, o atendimento é para o cliente do pacote, não para o número inicial
        context_update = {
            "tentativas_cpf_pacote": 0,
            "tipo_beneficio": "pacote",
            "codigo_cliente_pacote": codigo_cliente,
            "codigo_usuario": codigo_cliente,  # Atualiza para o cliente do pacote
            "nome": cliente.get("nome"),
            "cpf": cliente.get("cpf"),
            "celular": cliente.get("celular"),
            "email": cliente.get("email"),
            "dtNascimento": cliente.get("dtNascimento"),
            "genero": cliente.get("sexo"),  # API retorna 'sexo'
            "cadastro_completo": True
        }
        update_context(conversation_id, context_update)
        
        print(f"DEBUG - Cliente do pacote atualizado no contexto:")
        print(f"  - Código: {codigo_cliente}")
        print(f"  - Nome: {cliente.get('nome')}")
        print(f"  - CPF: {cliente.get('cpf')}")
        print(f"  - Celular: {cliente.get('celular')}")
        
        # Formata resultado
        resultado = "✅ <strong>Pacotes encontrados:</strong>\n\n"
        
        for idx, plano in enumerate(planos, 1):
            nome_plano = plano.get('nome', 'Pacote sem nome')
            cod_plano = plano.get('codPlano')  # 🔥 CAPTURA codPlano
            servicos = plano.get('servicos', [])
            
            resultado += f"<strong>📦 Pacote {idx}:</strong> {nome_plano}\n"
            
            if servicos:
                resultado += "   <strong>Terapias disponíveis:</strong>"
                terapias_lista = []
                
                print(f"DEBUG - Processando {len(servicos)} serviços do pacote")
                print(f"DEBUG - codPlano: {cod_plano}")
                
                for idx_servico, servico in enumerate(servicos, 1):
                    nome_servico = servico.get('nome')
                    cod_servico = servico.get('codServico')
                    saldo = servico.get('saldoRestante', '0')
                    
                    print(f"DEBUG - Serviço {idx_servico}: nome={nome_servico}, codServico={cod_servico}, saldo={saldo}")
                    
                    resultado += f"\n   {idx_servico}. {nome_servico} - Saldo: {saldo}"
                    terapias_lista.append(nome_servico)
                
                # 🔥 CRÍTICO: Armazena codPlano e nome_plano para descontar do saldo corretamente
                update_context(conversation_id, {
                    "terapias_disponiveis": terapias_lista,
                    "cod_plano": cod_plano,
                    "nome_plano": nome_plano
                })
                print(f"DEBUG - Terapias armazenadas no contexto: {terapias_lista}")
                print(f"DEBUG - codPlano armazenado: {cod_plano}")
                print(f"DEBUG - nome_plano armazenado: {nome_plano}")
            
            resultado += "\n\n"
        
        resultado += "O que deseja utilizar?"
        return resultado
        
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 404:
            tentativas_cpf += 1
            update_context(conversation_id, {"tentativas_cpf_pacote": tentativas_cpf})
            
            if tentativas_cpf >= 2:
                update_context(conversation_id, {"tentativas_cpf_pacote": 0})
                return """❌ CPF não encontrado novamente.

Infelizmente não conseguimos localizar pacotes ativos para este CPF.

Por favor, entre em contato com a nossa unidade para mais informações:
📞 (11) 3796-7799
📱 WhatsApp: (11) 97348-5060
🌐 https://buddhaspa.com.br/

Até mais! 👋"""
            
            return "❌ CPF não encontrado. Deseja tentar novamente?"
        
        return f"❌ Erro ao consultar pacotes: {str(e)}"
    except Exception as e:
        print(f"ERRO: {e}")
        import traceback
        traceback.print_exc()
        return f"❌ Erro inesperado: {str(e)}"

@Tool
def armazenar_nome_informado(ctx: RunContext[MyDeps], nome: str) -> str:
    """
    Armazena o nome informado pelo usuário no início da conversa.
    Use esta tool quando o usuário informar seu nome na primeira interação.
    
    Args:
        nome: Nome informado pelo usuário
    """
    conversation_id = ctx.deps.session_id
    
    print("=" * 80)
    print("🔍 TOOL: armazenar_nome_informado")
    print(f"Conversation ID: {conversation_id}")
    print(f"Nome informado: {nome}")
    print("=" * 80)
    
    # Armazena em variável separada (não sobrescreve o nome do cadastro)
    update_context(conversation_id, {
        "nome_informado": nome
    })
    
    print(f"✅ Nome '{nome}' armazenado no contexto!")
    print("=" * 80)
    
    return f"✅ Nome '{nome}' registrado com sucesso!"

@Tool
def armazenar_terapia(ctx: RunContext[MyDeps], terapia: str) -> str:
    """
    Armazena a terapia escolhida pelo usuário no contexto.
    Use esta tool quando o usuário escolher uma terapia do pacote.
    
    Args:
        terapia: Nome da terapia escolhida
    """
    conversation_id = ctx.deps.session_id
    
    print("=" * 80)
    print("DEBUG ARMAZENAR_TERAPIA")
    print(f"Conversation ID: {conversation_id}")
    print(f"Terapia: {terapia}")
    print("=" * 80)
    
    # Busca o codigo_servico primeiro em variacoes_terapia (VALE), depois em API de planos (PACOTE)
    session = get_session(conversation_id)
    context = session[2] if session else {}
    
    if isinstance(context, str):
        try:
            context = json.loads(context) if context else {}
        except:
            context = {}
    
    codigo_servico = None
    
    print(f"DEBUG - Buscando codServico para terapia '{terapia}'")
    
    # PRIORIDADE 1: Buscar em variacoes_terapia (para VALE)
    variacoes = context.get('variacoes_terapia', [])
    if variacoes:
        print(f"DEBUG - Buscando em variacoes_terapia ({len(variacoes)} variações)")
        for variacao in variacoes:
            if variacao.get('nome') == terapia:
                codigo_servico = variacao.get('codServico')
                print(f"DEBUG - ✅ codServico encontrado em variacoes_terapia: {codigo_servico} para terapia '{terapia}'")
                break
    
    # PRIORIDADE 2: Se não encontrou, buscar na API de planos (para PACOTE)
    if not codigo_servico:
        codigo_cliente = context.get('codigo_cliente_pacote') or context.get('codigo_usuario')
        print(f"DEBUG - Código cliente (pacote): {context.get('codigo_cliente_pacote')}")
        print(f"DEBUG - Código usuário (contexto): {context.get('codigo_usuario')}")
        print(f"DEBUG - Código usado para consulta: {codigo_cliente}")
        
        if codigo_cliente:
            try:
                headers = {'Authorization': os.getenv("LABELLE_TOKEN")}
                url_planos = f'https://app.bellesoftware.com.br/api/release/controller/IntegracaoExterna/v1.0/cliente/planos?codCliente={codigo_cliente}&codEstab=1'
                
                print(f"DEBUG - Consultando planos: {url_planos}")
                
                response = requests.get(url_planos, headers=headers)
                response.raise_for_status()
                planos = response.json()
                
                print(f"DEBUG - Planos retornados: {planos}")
                
                # Busca o codServico da terapia escolhida
                for plano in planos:
                    servicos = plano.get('servicos', [])
                    for servico in servicos:
                        if servico.get('nome') == terapia:
                            codigo_servico = servico.get('codServico')
                            print(f"DEBUG - ✅ codServico encontrado na API de planos: {codigo_servico} para terapia '{terapia}'")
                            break
                    if codigo_servico:
                        break
                
                if not codigo_servico:
                    print(f"DEBUG - ⚠️ codServico NÃO encontrado para terapia '{terapia}'")
            except Exception as e:
                print(f"DEBUG - ❌ Erro ao buscar codServico: {e}")
    
    # Armazena terapia E codigo_servico
    update_context(conversation_id, {
        "terapia": terapia,
        "codigo_servico": codigo_servico
    })
    ctx.deps.terapia = terapia
    
    print(f"✅ Terapia '{terapia}' armazenada no contexto!")
    print(f"✅ Código de serviço '{codigo_servico}' armazenado no contexto!")
    print("=" * 80)
    
    return f"✅ Terapia '{terapia}' selecionada com sucesso!"

@Tool
def ir_para_cadastro(ctx: RunContext[MyDeps]) -> str:
    """
    Transição do voucher_agent para cadastro_agent.
    Só deve ser chamada após validar benefício com sucesso.
    
    VERIFICAÇÃO CRÍTICA:
    - OBRIGATÓRIO: tipo_beneficio DEVE estar preenchido (voucher/pacote/vale)
    - Se benefício = voucher/pacote → DEVE ter terapia escolhida
    - Se benefício = vale bem-estar → pode prosseguir sem terapia (será escolhida depois)
    """
    conversation_id = ctx.deps.session_id
    tipo_beneficio = ctx.deps.tipo_beneficio if hasattr(ctx.deps, 'tipo_beneficio') else None
    terapia = ctx.deps.terapia if hasattr(ctx.deps, 'terapia') else None
    
    print("=" * 80)
    print("DEBUG IR_PARA_CADASTRO - VERIFICAÇÃO")
    print(f"Conversation ID: {conversation_id}")
    print(f"Tipo benefício: {tipo_beneficio}")
    print(f"Terapia escolhida: {terapia}")
    print("=" * 80)
    
    # 🔥 VALIDAÇÃO 1: tipo_beneficio OBRIGATÓRIO
    if not tipo_beneficio:
        print("❌ ERRO CRÍTICO: Tentativa de transição sem tipo_beneficio!")
        return (
            "❌ ERRO INTERNO: Benefício não foi validado corretamente.\n\n"
            f"Por favor, entre em contato com a nossa unidade:\n"
            f"📞 11 99999-9999"
        )
    
    # 🔥 VALIDAÇÃO 2: voucher/pacote DEVE ter terapia
    if tipo_beneficio in ['voucher', 'pacote']:
        if not terapia:
            print("❌ ERRO: Tentativa de transição sem terapia escolhida!")
            return (
                "❌ ERRO INTERNO: Não é possível prosseguir sem terapia escolhida.\n\n"
                f"Por favor, entre em contato com a nossa unidade:\n"
                f"📞 11 99999-9999"
            )
    
    update_current_agent(conversation_id, "cadastro_agent")
    
    print("✅ Transição para cadastro_agent realizada com sucesso!")
    
    return ""

# ============================================================================
# TOOLS - CADASTRO
# ============================================================================

@Tool
def consult_cadastro(ctx: RunContext[MyDeps], celular: str) -> dict:
    """Verifica se o número de celular já está cadastrado no sistema.

    Além de consultar a Belle, esta função normaliza os dados do cliente e
    já informa claramente quais campos obrigatórios do cadastro estão faltando.

    Args:
        celular (str): Número de celular a ser verificado.

    Returns:
        dict: Resultado padronizado da consulta.
    """
    conversation_id = ctx.deps.session_id
    
    print("=" * 80)
    print("DEBUG CONSULT_CADASTRO - INÍCIO")
    print(f"Conversation ID: {conversation_id}")
    print(f"Celular: {celular}")
    print("=" * 80)
    
    url = f'https://app.bellesoftware.com.br/api/release/controller/IntegracaoExterna/v1.0/cliente/listar?codEstab=1&celular={celular}'
    headers = {
        'Authorization': os.getenv("LABELLE_TOKEN")
    }

    resultado_vazio = {
        "encontrado": False,
        "dados_cliente": {},
        "campos_faltantes": CAMPOS_CADASTRO_OBRIGATORIOS.copy(),
        "campos_preenchidos": [],
        "cadastro_completo": False
    }
    
    print(f"DEBUG - resultado_vazio preparado: {resultado_vazio}")

    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()

        data = response.json()
        print(f"Resultado bruto da consulta de cadastro: {data}")

        dados_cliente = _normalizar_cliente_belle(data, celular_consultado=celular)
        print(f"DEBUG - dados_cliente normalizados: {dados_cliente}")

        if not dados_cliente:
            print("Cadastro não encontrado na Belle.")
            
            # Atualiza contexto mesmo quando não encontra cadastro
            print(f"DEBUG - Atualizando contexto com campos_faltantes: {resultado_vazio['campos_faltantes']}")
            print(f"DEBUG - Atualizando contexto com cadastro_completo: {resultado_vazio['cadastro_completo']}")
            
            if conversation_id:
                context_update = {
                    "campos_faltantes": resultado_vazio["campos_faltantes"],
                    "cadastro_completo": resultado_vazio["cadastro_completo"]
                }
                print(f"DEBUG - Chamando update_context com: {context_update}")
                update_context(conversation_id, context_update)
                print("DEBUG - update_context executado!")
            else:
                print("DEBUG - conversation_id é None, contexto NÃO atualizado!")
            
            print("=" * 80)
            return resultado_vazio

        analise = verificar_campos_faltantes_cadastro(dados_cliente)

        resultado = {
            "encontrado": True,
            **analise
        }

        if conversation_id:
            context_update = {
                chave: valor
                for chave, valor in analise["dados_cliente"].items()
                if _valor_preenchido(valor)
            }
            context_update["campos_faltantes"] = analise["campos_faltantes"]
            context_update["cadastro_completo"] = analise["cadastro_completo"]

            update_context(conversation_id, context_update)

        print(f"Resultado padronizado da consulta de cadastro: {resultado}")
        return resultado

    except Exception as e:
        print(f"Erro ao consultar cadastro: {e}")
        return {
            "erro": "Não foi possível consultar o cadastro no momento",
            **resultado_vazio
        }

@Tool
def validar_cpf_cadastro(
    ctx: RunContext[MyDeps],
    cpf: str
) -> str:
    """Valida CPF (formato, dígitos verificadores e duplicidade na API Belle).
    
    Use esta tool SEMPRE que o usuário informar um CPF durante o cadastro.
    
    Args:
        cpf: CPF informado pelo usuário
        
    Returns:
        str: "VALIDO" se CPF é válido e não está cadastrado
             "INVALIDO|mensagem_erro" se CPF é inválido ou já cadastrado
    """
    print("=" * 80)
    print("🔍 VALIDAR_CPF_CADASTRO")
    print(f"CPF recebido: {cpf}")
    
    # ETAPA 1: Normalizar CPF (remover pontos, traços, espaços)
    cpf_numeros = _somente_numeros(cpf)
    print(f"CPF normalizado: {cpf_numeros}")
    
    # ETAPA 2: Validar formato (11 dígitos)
    if not cpf_numeros or len(cpf_numeros) != 11:
        print(f"❌ CPF inválido: deve ter 11 dígitos (tem {len(cpf_numeros)})")
        print("=" * 80)
        return f"INVALIDO|CPF deve ter 11 dígitos"
    
    # ETAPA 3: Validar se não são todos dígitos iguais
    if cpf_numeros == cpf_numeros[0] * 11:
        print(f"❌ CPF inválido: todos os dígitos são iguais")
        print("=" * 80)
        return "INVALIDO|CPF inválido"
    
    # ETAPA 4: Validar dígitos verificadores
    # Primeiro dígito verificador
    soma = sum(int(cpf_numeros[i]) * (10 - i) for i in range(9))
    resto = soma % 11
    digito1 = 0 if resto < 2 else 11 - resto
    
    if int(cpf_numeros[9]) != digito1:
        print(f"❌ CPF inválido: primeiro dígito verificador incorreto")
        print("=" * 80)
        return "INVALIDO|CPF inválido"
    
    # Segundo dígito verificador
    soma = sum(int(cpf_numeros[i]) * (11 - i) for i in range(10))
    resto = soma % 11
    digito2 = 0 if resto < 2 else 11 - resto
    
    if int(cpf_numeros[10]) != digito2:
        print(f"❌ CPF inválido: segundo dígito verificador incorreto")
        print("=" * 80)
        return "INVALIDO|CPF inválido"
    
    print("✅ CPF válido (formato e dígitos verificadores)")
    
    # ETAPA 5: Verificar duplicidade na API Belle
    headers = {'Authorization': os.getenv("LABELLE_TOKEN")}
    url = f'https://app.bellesoftware.com.br/api/release/controller/IntegracaoExterna/v1.0/cliente/listar?cpf={cpf_numeros}&id=&codEstab=1&email=&celular='
    
    try:
        print(f"Verificando duplicidade na API Belle...")
        print(f"URL: {url}")
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        
        data = response.json()
        print(f"Resposta API: {json.dumps(data, ensure_ascii=False, indent=2)}")
        
        # API retorna um OBJETO com "codigo" quando encontra cadastro
        # API retorna {"msg": "..."} quando NÃO encontra
        
        if isinstance(data, dict) and "codigo" in data:
            nome = data.get("nome", "")
            print(f"❌ CPF já cadastrado para: {nome}")
            print("=" * 80)
            return f"INVALIDO|CPF já cadastrado no sistema para {nome}"
        
        # CPF não encontrado = disponível
        elif isinstance(data, dict) and "msg" in data:
            print(f"✅ CPF disponível (não cadastrado)")
            print("=" * 80)
            return "VALIDO"
        
        elif isinstance(data, list) and len(data) == 0:
            print(f"✅ CPF disponível (não cadastrado)")
            print("=" * 80)
            return "VALIDO"
        
        # Caso inesperado - por segurança, considerar disponível
        else:
            print(f"⚠️ Resposta inesperada da API: {type(data)}")
            print("✅ Considerando CPF disponível")
            print("=" * 80)
            return "VALIDO"
            
    except Exception as e:
        print(f"❌ Erro ao verificar duplicidade: {e}")
        print("=" * 80)
        return "INVALIDO|Não foi possível verificar o CPF no momento"

@Tool
def valida_cpf_email_telefone(cpf: str, email: str, telefone: str) -> object:
    """Valida CPF, email e telefone do usuário.
    Usar somente quando o usuário informar/confirmar os seguintes dados: CPF, telefone e e-mail.
    Nunca invente esses dados, usar somente quando o usuário informar.
    
    Args:
        cpf: CPF do usuário
        email: E-mail do usuário
        telefone: Telefone do usuário
        
    Returns:
        object: Resultado da validação
    """
    return {
        "cpf_valido": bool(cpf and len(_normalizar_cpf(cpf)) == 11),
        "email_valido": bool(email and "@" in email),
        "telefone_valido": bool(telefone and len(_normalizar_celular(telefone)) >= 10),
        "mensagem": "Dados validados com sucesso!"
    }

@Tool
def armazenar_dados_cadastro(
    ctx: RunContext[MyDeps],
    nome: str | None = None,
    cpf: str | None = None,
    celular: str | None = None,
    email: str | None = None,
    dtNascimento: str | None = None,
    genero: str | None = None
) -> str:
    """Armazena os dados de cadastro coletados no contexto da conversa.
    
    Use esta tool para salvar cada dado coletado do usuário durante o cadastro.
    
    Args:
        nome: Nome completo
        cpf: CPF (apenas números)
        celular: Celular (apenas números com DDD)
        email: E-mail
        dtNascimento: Data de nascimento (DD/MM/AAAA)
        genero: Gênero (Masculino/Feminino)
        
    Returns:
        str: Confirmação de armazenamento
    """
    conversation_id = ctx.deps.session_id
    
    print("=" * 80)
    print("DEBUG ARMAZENAR_DADOS_CADASTRO")
    print(f"Conversation ID: {conversation_id}")
    
    context_update = {}
    
    if nome:
        context_update["nome"] = nome
        print(f"  Nome armazenado: {nome}")
    
    if cpf:
        cpf_limpo = _somente_numeros(cpf)
        context_update["cpf"] = cpf_limpo
        print(f"  CPF armazenado: {cpf_limpo}")
    
    if celular:
        celular_limpo = _somente_numeros(celular)
        context_update["celular"] = celular_limpo
        print(f"  Celular armazenado: {celular_limpo}")
    
    if email:
        context_update["email"] = email
        print(f"  Email armazenado: {email}")
    
    if dtNascimento:
        context_update["dtNascimento"] = dtNascimento
        print(f"  Data nascimento armazenada: {dtNascimento}")
    
    if genero:
        context_update["genero"] = genero
        print(f"  Gênero armazenado: {genero}")
    
    if context_update:
        update_context(conversation_id, context_update)
        print("  Contexto atualizado com sucesso!")
        print("=" * 80)
        return "✅ Dados armazenados"
    else:
        print("  Nenhum dado para armazenar")
        print("=" * 80)
        return "⚠️ Nenhum dado informado"

@Tool
def criar_cadastro_cliente(
    ctx: RunContext[MyDeps],
    nome: str,
    cpf: str,
    celular: str,
    email: str,
    dtNascimento: str | None = None,
    genero: str | None = None
) -> str:
    """Cria um novo cadastro de cliente no sistema Belle.
    
    Use esta tool APENAS quando todos os dados obrigatórios foram coletados.
    
    Args:
        nome: Nome completo
        cpf: CPF (apenas números)
        celular: Celular (apenas números com DDD)
        email: E-mail
        dtNascimento: Data de nascimento (DD/MM/AAAA) - opcional
        genero: Gênero (Masculino/Feminino) - opcional
        
    Returns:
        str: Mensagem de sucesso ou erro
    """
    conversation_id = ctx.deps.session_id
    
    print("=" * 80)
    print("DEBUG CRIAR_CADASTRO_CLIENTE")
    print(f"Nome: {nome}")
    print(f"CPF: {cpf}")
    print(f"Celular: {celular}")
    print(f"Email: {email}")
    print(f"Data Nascimento: {dtNascimento}")
    print(f"Gênero: {genero}")
    print("=" * 80)
    
    url = 'https://app.bellesoftware.com.br/api/release/controller/IntegracaoExterna/v1.0/cliente/gravar'
    headers = {
        'Authorization': os.getenv("LABELLE_TOKEN"),
        'Content-Type': 'application/json'
    }
    
    payload = {
        "nome": nome,
        "ddiCelular": "+55",
        "celular": _somente_numeros(celular),
        "email": email,
        "cpf": _somente_numeros(cpf),
        "observacao": "Cadastro realizado via WhatsApp",
        "tpOrigem": "WhatsApp",
        "codOrigem": "99",
        "codEstab": 1
    }
    
    try:
        print(f"Enviando POST para: {url}")
        print(f"Payload: {payload}")
        
        response = requests.post(url, headers=headers, json=payload)
        response.raise_for_status()
        
        result = response.json()
        codigo_usuario = result.get("codigo")
        
        print(f"Cadastro criado! Código: {codigo_usuario}")
        
        # Atualizar contexto com código do usuário
        context_update = {
            "codigo_usuario": codigo_usuario,
            "nome": nome,
            "cpf": _somente_numeros(cpf),
            "celular": _somente_numeros(celular),
            "email": email,
            "cadastro_completo": True
        }
        
        if dtNascimento:
            context_update["dtNascimento"] = dtNascimento
        
        if genero:
            context_update["genero"] = genero
        
        # Se tem dtNascimento ou genero, complementar cadastro
        if codigo_usuario and (dtNascimento or genero):
            print("Complementando cadastro com dtNascimento/genero...")
            url_update = f'https://app.bellesoftware.com.br/api/release/controller/IntegracaoExterna/v1.0/cliente?codCliente={codigo_usuario}'
            
            payload_update = {}
            if dtNascimento:
                payload_update["dataNascimento"] = dtNascimento
            if genero:
                payload_update["genero"] = genero
            
            try:
                response_update = requests.put(url_update, headers=headers, json=payload_update)
                response_update.raise_for_status()
                print("Cadastro complementado com sucesso!")
            except Exception as e:
                print(f"Erro ao complementar cadastro: {e}")
        
        update_context(conversation_id, context_update)
        
        # Atualiza ctx.deps para que ir_para_agendamento possa acessar
        ctx.deps.codigo_usuario = codigo_usuario
        ctx.deps.nome = nome
        ctx.deps.cpf = _somente_numeros(cpf)
        ctx.deps.celular = _somente_numeros(celular)
        ctx.deps.email = email
        ctx.deps.cadastro_completo = True
        if dtNascimento:
            ctx.deps.dtNascimento = dtNascimento
        if genero:
            ctx.deps.genero = genero
        
        print(f"✅ ctx.deps atualizado: codigo_usuario={ctx.deps.codigo_usuario}")
        print("=" * 80)
        
        return "✅ Cadastro criado com sucesso!"
        
    except Exception as e:
        print(f"Erro ao criar cadastro: {e}")
        print(f"Response: {response.text if 'response' in locals() else 'N/A'}")
        print("=" * 80)
        return f"❌ Erro ao criar cadastro: {str(e)}"

@Tool
def atualizar_cadastro_cliente(
    ctx: RunContext[MyDeps],
    codigo_usuario: int,
    nome: str | None = None,
    cpf: str | None = None,
    celular: str | None = None,
    email: str | None = None,
    dtNascimento: str | None = None,
    genero: str | None = None
) -> str:
    """Atualiza o cadastro de um cliente existente.
    
    Args:
        codigo_usuario: Código do usuário na Belle
        nome: Nome completo
        cpf: CPF
        celular: Celular
        email: E-mail
        dtNascimento: Data de nascimento (DD/MM/AAAA)
        genero: Gênero (Masculino/Feminino)
        
    Returns:
        str: Mensagem de sucesso ou erro
    """
    conversation_id = ctx.deps.session_id
    
    print("=" * 80)
    print("DEBUG ATUALIZAR_CADASTRO_CLIENTE")
    print(f"Código usuário: {codigo_usuario}")
    print("=" * 80)
    
    url = f'https://app.bellesoftware.com.br/api/release/controller/IntegracaoExterna/v1.0/cliente?codCliente={codigo_usuario}'
    headers = {
        'Authorization': os.getenv("LABELLE_TOKEN"),
        'Content-Type': 'application/json'
    }
    
    payload = {}
    context_update = {}
    
    if nome:
        payload["nome"] = nome
        context_update["nome"] = nome
    
    if cpf:
        cpf_limpo = _somente_numeros(cpf)
        payload["cpf"] = cpf_limpo
        context_update["cpf"] = cpf_limpo
    
    if celular:
        celular_limpo = _somente_numeros(celular)
        payload["celular"] = celular_limpo
        context_update["celular"] = celular_limpo
    
    if email:
        payload["email"] = email
        context_update["email"] = email
    
    if dtNascimento:
        payload["dataNascimento"] = dtNascimento
        context_update["dtNascimento"] = dtNascimento
    
    if genero:
        payload["genero"] = genero
        context_update["genero"] = genero
    
    if not payload:
        return "⚠️ Nenhum dado para atualizar"
    
    try:
        print(f"Enviando PUT para: {url}")
        print(f"Payload: {payload}")
        
        response = requests.put(url, headers=headers, json=payload)
        response.raise_for_status()
        
        context_update["codigo_usuario"] = codigo_usuario
        context_update["cadastro_completo"] = True
        
        update_context(conversation_id, context_update)
        
        print("Cadastro atualizado com sucesso!")
        print("=" * 80)
        
        return "✅ Cadastro atualizado com sucesso!"
        
    except Exception as e:
        print(f"Erro ao atualizar cadastro: {e}")
        print(f"Response: {response.text if 'response' in locals() else 'N/A'}")
        print("=" * 80)
        return f"❌ Erro ao atualizar cadastro: {str(e)}"

@Tool
def encerrar_atendimento(
    ctx: RunContext[MyDeps],
    motivo: str = "finalizado",
    mensagem_usuario: str | None = None
) -> str:
    """Encerra o atendimento de forma controlada, deletando a sessão e limpando recursos.
    
    Use esta tool quando:
    - Usuário falhou 3 tentativas de validação (nome, CPF, email, etc)
    - Erro crítico que impede continuação
    - Atendimento foi concluído com sucesso
    - Usuário solicitou cancelamento
    
    Args:
        motivo: Motivo do encerramento (ex: "validacao_falhou", "erro_critico", "concluido", "cancelado")
        mensagem_usuario: Mensagem personalizada para o usuário (opcional)
        
    Returns:
        str: Mensagem de confirmação do encerramento
    """
    from store.database import delete_session, get_session
    
    conversation_id = ctx.deps.session_id
    
    print("=" * 80)
    print("🔴 ENCERRAR_ATENDIMENTO - INÍCIO")
    print(f"Conversation ID: {conversation_id}")
    print(f"Motivo: {motivo}")
    print(f"Mensagem customizada: {mensagem_usuario}")
    print("=" * 80)
    
    try:
        # Obter dados da sessão antes de deletar (para log)
        session = get_session(conversation_id)
        if session:
            current_agent = session[1]
            context = session[2] or {}
            print(f"📊 Dados da sessão antes de encerrar:")
            print(f"   Agente atual: {current_agent}")
            print(f"   Contexto: {context}")
        
        # Deletar sessão
        delete_session(conversation_id)
        print(f"✅ Sessão {conversation_id} deletada com sucesso.")
        print(f"🔴 Motivo do encerramento: {motivo}")
        print("=" * 80)
        
        # Retornar mensagem apropriada
        if mensagem_usuario:
            return mensagem_usuario
        
        # Mensagens padrão baseadas no motivo
        mensagens_padrao = {
            "validacao_falhou": (
                "Não foi possível validar os dados após algumas tentativas. "
                "Para seguir, entre em contato com a unidade:\n\n"
                "📞 (11) 3796-7799\n"
                "📱 WhatsApp: (11) 97348-5060"
            ),
            "erro_critico": (
                "Ops, algo deu errado. Por favor, entre em contato com nossa unidade:\n\n"
                "📞 (11) 3796-7799\n"
                "📱 WhatsApp: (11) 97348-5060"
            ),
            "concluido": "✅ Atendimento finalizado com sucesso!",
            "cancelado": "Atendimento cancelado. Até logo! 👋",
            "timeout": (
                "O tempo de atendimento expirou. "
                "Inicie uma nova conversa quando desejar. 👋"
            )
        }
        
        return mensagens_padrao.get(motivo, "Atendimento encerrado.")
        
    except Exception as e:
        print(f"❌ Erro ao encerrar atendimento: {e}")
        print("=" * 80)
        return f"Erro ao encerrar atendimento: {str(e)}"

@Tool
def ir_para_agendamento(ctx: RunContext[MyDeps]) -> str:
    """
    Transição do cadastro_agent para agendamento_agent.
    
    Validações:
    - Deve ter cadastro (codigo_usuario)
    - Deve ter tipo_beneficio definido (voucher, pacote ou vale)
    - Se voucher ou pacote: deve ter terapia selecionada
    - Se vale: não precisa de terapia (vai escolher no agendamento)
    
    Returns:
        str: Mensagem de transição ou erro de validação
    """
    from store.database import update_current_agent
    
    conversation_id = ctx.deps.session_id
    codigo_usuario = ctx.deps.codigo_usuario
    tipo_beneficio = ctx.deps.tipo_beneficio
    terapia = ctx.deps.terapia
    em_reagendamento = getattr(ctx.deps, 'em_reagendamento', False)
    
    print("=" * 80)
    print("DEBUG IR_PARA_AGENDAMENTO - VERIFICAÇÃO")
    print(f"Conversation ID: {conversation_id}")
    print(f"Código usuário: {codigo_usuario}")
    print(f"Tipo benefício: {tipo_beneficio}")
    print(f"Terapia: {terapia}")
    print(f"Em reagendamento: {em_reagendamento}")
    print("=" * 80)
    
    # Se está em reagendamento, pula todas as validações
    if em_reagendamento:
        print("🔄 REAGENDAMENTO DETECTADO - Pulando validações de tipo_beneficio e terapia")
        print("=" * 80)
        # Atualiza agente para agendamento_agent
        try:
            update_current_agent(conversation_id, "agendamento_agent")
            print(f"✅ Transição para agendamento_agent realizada com sucesso!")
            print("=" * 80)
            
            # Retorna vazio para trigger de transição no app.py
            return ""
            
        except Exception as e:
            print(f"❌ Erro ao atualizar agente: {e}")
            print("=" * 80)
            return f"❌ Erro ao transicionar para agendamento: {str(e)}"
    
    # Validação 1: Deve ter cadastro
    if not codigo_usuario:
        return "❌ Erro: Cadastro não encontrado. Complete o cadastro antes de agendar."
    
    # Validação 2: Deve ter tipo de benefício
    if not tipo_beneficio:
        return "❌ Erro: Tipo de benefício não identificado. Reinicie o processo."
    
    # Validação 3: Voucher e Pacote precisam de terapia
    if tipo_beneficio in ["voucher", "pacote"]:
        if not terapia:
            return "❌ Erro: Terapia não selecionada. Complete a seleção antes de agendar."
        
        print(f"✅ Validação OK - {tipo_beneficio.upper()} com terapia: {terapia}")
    
    # Validação 4: Vale bem-estar não precisa de terapia (vai escolher no agendamento)
    elif tipo_beneficio == "vale":
        print("✅ Validação OK - VALE BEM-ESTAR (terapia será escolhida no agendamento)")
    
    else:
        return f"❌ Erro: Tipo de benefício '{tipo_beneficio}' não reconhecido."
    
    # Atualiza agente para agendamento_agent
    try:
        update_current_agent(conversation_id, "agendamento_agent")
        print(f"✅ Transição para agendamento_agent realizada com sucesso!")
        print("=" * 80)
        
        # Retorna vazio para trigger de transição no app.py
        return ""
        
    except Exception as e:
        print(f"❌ Erro ao atualizar agente: {e}")
        print("=" * 80)
        return f"❌ Erro ao transicionar para agendamento: {str(e)}"

# @Tool
# def delete_conversation(conversation_id: str) -> str:
#     """Deleta uma sessão de conversa e encerra a conversa.

#     Args:
#         conversation_id (str): ID da conversa a ser deletada.

#     Returns:
#         str: Mensagem de confirmação ou erro.
#     """
#     from store.database import delete_session
    
#     try:
#         delete_session(conversation_id)
#         print(f"Sessão {conversation_id} deletada com sucesso.")
#         return "Sessão deletada com sucesso."
#     except Exception as e:
#         print(f"Erro ao deletar sessão: {e}")
#         return f"Erro ao deletar sessão: {e}"

@Tool
def validar_terapia_vale(
    ctx: RunContext[MyDeps],
    nome_terapia: str
) -> str:
    """
    Valida se uma terapia mencionada pelo usuário existe e se o valor do vale bem-estar cobre.
    
    Busca todas as terapias disponíveis na API e verifica:
    1. Se a terapia existe (usando similaridade de nome)
    2. Se o valor do vale bem-estar cobre o valor da terapia
    
    Args:
        nome_terapia (str): Nome da terapia mencionada pelo usuário
        
    Returns:
        str: Mensagem indicando se a terapia existe e se o vale cobre o valor
    """
    import re
    from difflib import SequenceMatcher
    
    conversation_id = ctx.deps.session_id
    
    print("=" * 80)
    print("DEBUG VALIDAR_TERAPIA_VALE - INÍCIO")
    print(f"Conversation ID: {conversation_id}")
    print(f"Terapia mencionada: {nome_terapia}")
    print("=" * 80)
    
    # 🔥 MAPEAMENTO DE TERAPIAS PARA FILTRO DA API
    mapeamento_filtro = {
        "massagem relaxante": "relaxante",
        "relaxante": "relaxante",
        "brazilian massage": "brazilian",
        "brazilian": "brazilian",
        "shiatsu": "shiatsu",
        "massagem ayurvédica": "ayurvedica",
        "ayurvedica": "ayurvedica",
        "reflexologia": "reflexologia",
        "indian head": "indian head",
        "spa relax": "day spa",
        "day spa": "day spa",
        "mini day spa": "mini day spa",
        "experiência beauty & relax": "casal",
        "beauty & relax": "casal",
        "drenagem corporal": "drenagem",
        "drenagem": "drenagem",
        "massagem modeladora": "modeladora",
        "modeladora": "modeladora",
        "tratamentos faciais": "facial",
        "facial": "facial"
    }
    
    # Tenta encontrar filtro específico no mapeamento
    nome_normalizado = nome_terapia.lower().strip()
    filtro_especifico = mapeamento_filtro.get(nome_normalizado, "")
    
    # Se encontrou filtro específico, usa ele para buscar na API
    if filtro_especifico:
        print(f"✅ Filtro específico encontrado: '{filtro_especifico}'")
        url = f'https://app.bellesoftware.com.br/api/release/controller/IntegracaoExterna/v1.0/servico/listar?codPlano=&codProf=&codSala=&filtro={filtro_especifico}&codCategoria=&codTipo='
    else:
        print(f"⚠️ Filtro específico não encontrado, buscando todas as terapias")
        url = 'https://app.bellesoftware.com.br/api/release/controller/IntegracaoExterna/v1.0/servico/listar?codPlano=&codProf=&codSala=&filtro=&codCategoria=&codTipo='
    
    headers = {
        'Authorization': os.getenv("LABELLE_TOKEN")
    }
    
    try:
        response = requests.get(url, headers=headers)
        
        if response.status_code != 200:
            print(f"❌ Erro na API: {response.status_code}")
            return "❌ Não foi possível consultar as terapias no momento. Por favor, tente novamente."
        
        terapias = response.json()
        print(f"Total de terapias encontradas: {len(terapias)}")
        
        # 🔥 SE USOU FILTRO ESPECÍFICO, PROCESSAR VARIAÇÕES DIRETAMENTE
        if filtro_especifico:
            print(f"✅ Processando variações do filtro '{filtro_especifico}'")
            
            # Remove variações de domingo e agrupa por nome base
            variacoes_unicas = {}
            for t in terapias:
                nome_completo = t.get('nome', '')
                
                # Pular variações de domingo
                if ' Dom' in nome_completo or ' DOM' in nome_completo or ' dom' in nome_completo:
                    continue
                
                # Usar nome completo como chave
                if nome_completo not in variacoes_unicas:
                    variacoes_unicas[nome_completo] = t
            
            variacoes = list(variacoes_unicas.values())
            variacoes.sort(key=lambda x: x.get('tempo', 0))
            
            print(f"✅ Encontradas {len(variacoes)} variações (sem domingo)")
            for v in variacoes:
                print(f"   - {v.get('nome')} ({v.get('tempo')} min) - R$ {v.get('valor')}")
            
            # Se houver MÚLTIPLAS variações, mostrar opções ao usuário
            if len(variacoes) > 1:
                print("🔄 Múltiplas variações encontradas - mostrando opções ao usuário")
                
                # Armazena as variações no contexto para referência futura
                update_context(conversation_id, {
                    "variacoes_terapia": [
                        {
                            "nome": v.get('nome'),
                            "codServico": v.get('codServico'),
                            "tempo": v.get('tempo'),
                            "valor": v.get('valor')
                        }
                        for v in variacoes
                    ]
                })
                
                # Monta lista numerada
                lista_opcoes = []
                for i, v in enumerate(variacoes, 1):
                    nome_v = v.get('nome')
                    tempo_v = v.get('tempo')
                    lista_opcoes.append(f"  {i}. {nome_v} ({tempo_v} minutos)")
                
                lista_opcoes_str = "\n".join(lista_opcoes)
                
                # Extrai nome base da terapia (sem números)
                nome_base = re.sub(r'\d+', '', variacoes[0].get('nome', '')).strip()
                
                return f"""✅ Encontrei a terapia <strong>{nome_base}</strong>!

Temos as seguintes opções de duração disponíveis:

{lista_opcoes_str}

Qual opção você prefere? 😊"""
            
            # Se houver APENAS UMA variação, prosseguir com validação do vale
            elif len(variacoes) == 1:
                print("✅ Apenas uma variação encontrada - validando com o vale")
                terapia_encontrada = variacoes[0]
                # Continua para validação do vale (código abaixo)
            else:
                print("❌ Nenhuma variação encontrada após filtrar domingo")
                return f"""❌ Não encontrei a terapia "<strong>{nome_terapia}</strong>" em nosso catálogo.

Por favor, verifique o nome ou escolha conhecer as opções disponíveis."""
        
        # 🔥 SE NÃO USOU FILTRO ESPECÍFICO, USA SIMILARIDADE
        else:
            # Função para limpar nome da terapia
            def limpar_nome(nome):
                nome = re.sub(r'\d+', '', nome)  # Remove números
                nome = nome.replace(' Dom', '').replace(' DOM', '')  # Remove "Dom"
                return nome.strip().lower()
            
            # Função para calcular similaridade
            def similaridade(a, b):
                return SequenceMatcher(None, a.lower(), b.lower()).ratio()
            
            # Extrai categorias únicas
            categorias_set = set()
            for t in terapias:
                cat = t.get('categoria', '')
                if cat:
                    categorias_set.add(cat)
            
            categorias = list(categorias_set)
            print(f"Total de categorias encontradas: {len(categorias)}")
            
            # Verifica se o usuário mencionou uma CATEGORIA
            nome_terapia_limpo = limpar_nome(nome_terapia)
            melhor_categoria = None
            melhor_score_categoria = 0
            
            for categoria in categorias:
                # Extrai apenas o nome da categoria (remove código)
                # Ex: "6 - Terapias Chinesas" -> "Terapias Chinesas"
                nome_categoria = categoria.split(' - ', 1)[1] if ' - ' in categoria else categoria
                nome_categoria_limpo = limpar_nome(nome_categoria)
                
                score = similaridade(nome_terapia_limpo, nome_categoria_limpo)
                
                if score > melhor_score_categoria:
                    melhor_score_categoria = score
                    melhor_categoria = categoria
            
            print(f"Melhor categoria match: {melhor_categoria}")
            print(f"Score categoria: {melhor_score_categoria}")
            
            # Procura terapia específica com maior similaridade
            melhor_match_terapia = None
            melhor_score_terapia = 0
            
            for terapia in terapias:
                nome_api = terapia.get('nome', '')
                nome_api_limpo = limpar_nome(nome_api)
                
                score = similaridade(nome_terapia_limpo, nome_api_limpo)
                
                if score > melhor_score_terapia:
                    melhor_score_terapia = score
                    melhor_match_terapia = terapia
            
            print(f"Melhor terapia match: {melhor_match_terapia.get('nome') if melhor_match_terapia else 'Nenhum'}")
            print(f"Score terapia: {melhor_score_terapia}")
            
            # DECISÃO: É CATEGORIA OU TERAPIA?
            # Se score de categoria for maior E >= 60%, é categoria
            if melhor_score_categoria >= 0.6 and melhor_score_categoria > melhor_score_terapia:
                print(f"✅ Usuário mencionou CATEGORIA: {melhor_categoria}")
                
                # Filtra terapias dessa categoria
                terapias_categoria = [t for t in terapias if t.get('categoria') == melhor_categoria]
                
                # Agrupa por nome base (remove " Dom" / " DOM" para evitar duplicatas)
                terapias_unicas = {}
                for t in terapias_categoria:
                    nome_completo = t.get('nome', '')
                    # Remove variações de domingo
                    nome_sem_dom = nome_completo.replace(' Dom', '').replace(' DOM', '').replace(' dom', '').strip()
                    
                    # Se ainda não existe, adiciona
                    if nome_sem_dom not in terapias_unicas:
                        terapias_unicas[nome_sem_dom] = t
                
                # Função para formatar nome com duração
                def formatar_terapia(nome, tempo):
                    import re
                    # Verifica se já tem número no nome (duração)
                    match = re.search(r'\b(\d+)\b', nome)
                    if match and tempo:
                        # Já tem número, adiciona " min" se for a duração
                        numero = match.group(1)
                        if int(numero) == tempo:
                            return nome.replace(numero, f"{numero} min")
                        return nome
                    elif tempo:
                        # Não tem número, adiciona duração
                        return f"{nome} ({tempo} min)"
                    return nome
                
                # Monta lista numerada de terapias com duração formatada
                lista_terapias = []
                for i, (nome_base, terapia_obj) in enumerate(sorted(terapias_unicas.items()), 1):
                    tempo = terapia_obj.get('tempo')
                    nome_formatado = formatar_terapia(nome_base, tempo)
                    lista_terapias.append(f"  {i}. {nome_formatado}")
                
                lista_terapias_str = "\n".join(lista_terapias)
                
                nome_categoria_display = melhor_categoria.split(' - ', 1)[1] if ' - ' in melhor_categoria else melhor_categoria
                
                # Armazena as terapias da categoria como variações para uso posterior
                update_context(conversation_id, {
                    "variacoes_terapia": [
                        {
                            "nome": t.get('nome'),
                            "codServico": t.get('codServico'),
                            "tempo": t.get('tempo'),
                            "valor": t.get('valor')
                        }
                        for t in terapias_categoria
                    ],
                    "aguardando_escolha_categoria": True
                })
                
                return f"""✅ Encontrei a categoria <strong>{nome_categoria_display}</strong>!

Aqui estão as terapias disponíveis:

{lista_terapias_str}

Qual dessas terapias você gostaria de agendar? 😊"""
            
            # Se não é categoria, verifica se é terapia específica
            if melhor_score_terapia < 0.6:
                print("❌ Nem categoria nem terapia encontrada (similaridade < 60%)")
                return f"""❌ Não encontrei a terapia "<strong>{nome_terapia}</strong>" em nosso catálogo.

Por favor, verifique o nome ou escolha conhecer as opções disponíveis."""
            
            # TERAPIA ESPECÍFICA ENCONTRADA
            print(f"✅ Usuário mencionou TERAPIA: {melhor_match_terapia.get('nome')}")
            
            # 🔥 BUSCAR TODAS AS VARIAÇÕES DA TERAPIA (diferentes durações)
            # Extrai nome base da terapia (sem duração e sem "Dom")
            nome_match = melhor_match_terapia.get('nome', '')
            nome_base_match = re.sub(r'\d+', '', nome_match).replace(' Dom', '').replace(' DOM', '').replace(' dom', '').strip()
            
            print(f"🔍 Buscando todas as variações de: {nome_base_match}")
            
            # Filtra todas as terapias com o mesmo nome base
            variacoes = []
            for t in terapias:
                nome_t = t.get('nome', '')
                nome_base_t = re.sub(r'\d+', '', nome_t).replace(' Dom', '').replace(' DOM', '').replace(' dom', '').strip()
                
                # Se o nome base é o mesmo E não é domingo
                if nome_base_t.lower() == nome_base_match.lower() and ' Dom' not in nome_t and ' DOM' not in nome_t and ' dom' not in nome_t:
                    variacoes.append(t)
            
            print(f"✅ Encontradas {len(variacoes)} variações (sem domingo)")
            for v in variacoes:
                print(f"   - {v.get('nome')} ({v.get('tempo')} min) - R$ {v.get('valor')}")
            
            # Se houver MÚLTIPLAS variações, mostrar opções ao usuário
            if len(variacoes) > 1:
                print("🔄 Múltiplas variações encontradas - mostrando opções ao usuário")
                
                # Ordena por tempo
                variacoes.sort(key=lambda x: x.get('tempo', 0))
                
                # Armazena as variações no contexto para referência futura
                update_context(conversation_id, {
                    "variacoes_terapia": [
                        {
                            "nome": v.get('nome'),
                            "codServico": v.get('codServico'),
                            "tempo": v.get('tempo'),
                            "valor": v.get('valor')
                        }
                        for v in variacoes
                    ]
                })
                
                # Monta lista numerada
                lista_opcoes = []
                for i, v in enumerate(variacoes, 1):
                    nome_v = v.get('nome')
                    tempo_v = v.get('tempo')
                    lista_opcoes.append(f"  {i}. {nome_v} ({tempo_v} minutos)")
                
                lista_opcoes_str = "\n".join(lista_opcoes)
                
                return f"""✅ Encontrei a terapia <strong>{nome_base_match}</strong>!

Temos as seguintes opções de duração disponíveis:

{lista_opcoes_str}

Qual opção você prefere? 😊"""
            
            # Se houver APENAS UMA variação, prosseguir com validação do vale
            print("✅ Apenas uma variação encontrada - validando com o vale")
            terapia_encontrada = variacoes[0] if variacoes else melhor_match_terapia
        
        # 🔥 CÓDIGO COMUM: Validação do vale (usado tanto para filtro específico quanto similaridade)
        codigo_servico = terapia_encontrada.get('codServico')
        nome_oficial = terapia_encontrada.get('nome')
        
        # 🔥 CORREÇÃO: Converte valor (formato "179,00" -> 179.00)
        valor_str = terapia_encontrada.get('valor', '0')
        valor_str = str(valor_str).replace('.', '').replace(',', '.')  # "179,00" -> "179.00"
        
        try:
            valor_terapia = float(valor_str)
        except ValueError as e:
            print(f"❌ Erro ao converter valor: {valor_str} - {e}")
            valor_terapia = 0.0
        
        print(f"✅ Terapia encontrada: {nome_oficial}")
        print(f"   Código: {codigo_servico}")
        print(f"   Valor: R$ {valor_terapia:.2f}")
        
        # Pega valor do vale do contexto
        session = get_session(conversation_id)
        context = session[2] if session else {}
        
        if isinstance(context, str):
            try:
                context = json.loads(context) if context else {}
            except:
                context = {}
        
        # Pega tipo do vale (Percentual ou Real)
        tipo_valor_vale = context.get('tipo_valor_vale', '')
        
        print(f"   Tipo do vale: {tipo_valor_vale}")
        
        # Armazena terapia no contexto
        context_update = {
            "terapia": nome_oficial,
            "codigo_servico": codigo_servico,
            "valor_terapia": valor_terapia
        }
        update_context(conversation_id, context_update)
        
        print(f"✅ Terapia armazenada no contexto: {nome_oficial}")
        print("=" * 80)
        
        # VALE PERCENTUAL - Sempre cobre (desconto percentual)
        if "Percentual" in tipo_valor_vale or "%" in tipo_valor_vale:
            print("✅ Vale é PERCENTUAL - Sempre cobre")
            return f"""✅ Tudo certo! Seu vale bem-estar cobre essa experiência. 😉

<strong>Terapia:</strong> {nome_oficial}

Vamos prosseguir para a escolha da data do agendamento."""
        
        # VALE REAL - Compara valores
        else:
            valor_vale_str = context.get('valor_vale', '0')
            
            # Remove caracteres não numéricos e converte
            valor_vale_str = str(valor_vale_str).replace('.', '').replace(',', '.')
            
            try:
                valor_vale = float(valor_vale_str)
            except:
                valor_vale = 0
            
            print(f"   Valor do vale: R$ {valor_vale:.2f}")
            print(f"   Valor da terapia: R$ {valor_terapia:.2f}")
            
            # Verifica se o vale cobre o valor
            if valor_vale >= valor_terapia:
                print("✅ Vale COBRE o valor da terapia")
                return f"""✅ Tudo certo! Seu vale bem-estar cobre essa experiência. 😉

<strong>Terapia:</strong> {nome_oficial}

Vamos prosseguir para a escolha da data do agendamento."""
            else:
                print("⚠️ Vale NÃO COBRE o valor da terapia")
                return f"""⚠️ Essa terapia pode ser realizada com o seu vale, porém será necessário acertar uma diferença diretamente na unidade no dia do atendimento.

<strong>Terapia:</strong> {nome_oficial}

Deseja continuar mesmo assim?"""
    
    except Exception as e:
        print(f"❌ Erro ao validar terapia: {e}")
        print("=" * 80)


def verificar_pergunta_valor(
    conversation_id: str,
    mensagem_usuario: str,
    ctx: MyDeps
) -> str:
    """
    Verifica se o usuário está perguntando sobre valor/diferença/preço.
    Se sim, retorna a resposta padrão com contato da unidade.
    Se não, retorna string vazia para que o agente continue normalmente.
    
    IMPORTANTE: Esta tool deve ser chamada ANTES de qualquer outra ação quando
    o usuário está no fluxo de vale bem-estar.
    """
    print("=" * 80)
    print(f"🔍 DEBUG VERIFICAR_PERGUNTA_VALOR")
    print(f"Conversation ID: {conversation_id}")
    print(f"Mensagem do usuário: {mensagem_usuario}")
    print("=" * 80)
    
    # Normaliza a mensagem para lowercase
    mensagem_lower = mensagem_usuario.lower().strip()
    
    # Lista de palavras-chave que indicam pergunta sobre valor
    palavras_chave_valor = [
        "diferença",
        "diferenca",
        "valor",
        "custa",
        "custo",
        "preço",
        "preco",
        "pagar",
        "quanto",
        "qual o valor",
        "qual a diferença",
        "qual a diferenca",
        "quanto é",
        "quanto e",
        "quanto custa"
    ]
    
    # Verifica se alguma palavra-chave está presente
    pergunta_sobre_valor = any(palavra in mensagem_lower for palavra in palavras_chave_valor)
    
    if pergunta_sobre_valor:
        print("✅ PERGUNTA SOBRE VALOR DETECTADA!")
        print(f"   Mensagem: {mensagem_usuario}")
        print("   Retornando resposta padrão com contato da unidade")
        print("=" * 80)
        
        return """Os valores são informados diretamente pela unidade.
Para esse detalhe, é necessário entrar em contato com nossa unidade.

📞 (11) 3796-7799
📱 WhatsApp: (11) 97348-5060

Deseja continuar com o agendamento mesmo assim?"""
    
    print("❌ NÃO é pergunta sobre valor")
    print("   Retornando string vazia para continuar fluxo normal")
    print("=" * 80)
    return ""

# ============================================================================
# CONSTANTES PARA EXPLICAÇÃO DE TERAPIAS
# ============================================================================

# Nomes exatos das terapias para apresentação
TERAPIAS_POR_CATEGORIA = {
    "Relaxamento corporal": [
        "Massagem Relaxante",
        "Brazilian Massage",
        "Shiatsu",
        "Massagem Ayurvédica",
        "Reflexologia",
        "Indian Head"
    ],
    "Experiências completas (Day Spa)": [
        "Spa Relax",
        "Mini Day Spa",
        "Experiência Beauty & Relax"
    ],
    "Estética corporal e facial": [
        "Drenagem corporal",
        "Massagem modeladora",
        "Tratamentos faciais"
    ]
}

EXPLICACOES_TERAPIAS = {
    # Relaxamento corporal
    "Massagem Relaxante": "A Massagem Relaxante é perfeita para aliviar tensões e promover bem-estar. Utiliza manobras suaves e ritmadas que relaxam a musculatura e acalmam a mente.",
    "Brazilian Massage": "A Brazilian Massage combina técnicas brasileiras de massagem com movimentos que estimulam a circulação e proporcionam profundo relaxamento muscular.",
    "Shiatsu": "O Shiatsu é uma técnica japonesa que utiliza pressão dos dedos em pontos específicos do corpo para equilibrar a energia vital e promover relaxamento profundo.",
    "Massagem Ayurvédica": "A Massagem Ayurvédica é uma técnica milenar indiana que utiliza óleos aromáticos e manobras específicas para equilibrar corpo, mente e espírito.",
    "Reflexologia": "A Reflexologia trabalha pontos reflexos nos pés que correspondem a órgãos e sistemas do corpo, promovendo equilíbrio e bem-estar geral.",
    "Indian Head": "O Indian Head é uma massagem indiana focada em cabeça, pescoço e ombros, ideal para aliviar tensões e dores de cabeça.",
    # Experiências completas (Day Spa)
    "Spa Relax": "O Spa Relax é uma experiência completa que combina diferentes terapias para proporcionar um dia inteiro de relaxamento e renovação.",
    "Mini Day Spa": "O Mini Day Spa oferece uma experiência condensada com as principais terapias do spa em um período menor, ideal para quem tem menos tempo disponível.",
    "Experiência Beauty & Relax": "A Experiência Beauty & Relax combina tratamentos estéticos e relaxantes para cuidar da beleza e do bem-estar ao mesmo tempo.",
    # Estética corporal e facial
    "Drenagem corporal": "A Drenagem corporal é uma técnica que estimula o sistema linfático, reduzindo inchaços, eliminando toxinas e melhorando a circulação.",
    "Massagem modeladora": "A Massagem modeladora utiliza manobras vigorosas para reduzir medidas, combater celulite e tonificar a pele.",
    "Tratamentos faciais": "Os Tratamentos faciais são procedimentos personalizados para cuidar da pele do rosto, promovendo limpeza profunda, hidratação e rejuvenescimento."
}

def _get_explicacao_terapia(nome_terapia: str) -> str:
    """
    Retorna a explicação de uma terapia específica.
    
    Args:
        nome_terapia: Nome da terapia (case-insensitive)
    
    Returns:
        Explicação da terapia ou mensagem padrão se não encontrada
    """
    for terapia, explicacao in EXPLICACOES_TERAPIAS.items():
        if terapia.lower() == nome_terapia.lower():
            return explicacao
    return f"A {nome_terapia} é uma excelente opção de terapia disponível em nosso spa."

def _buscar_variacoes_terapia(nome_terapia: str) -> list:
    """
    Busca todas as variações de uma terapia na API Belle usando o parâmetro filtro.
    Remove variações de domingo e agrupa variações duplicadas.
    
    Args:
        nome_terapia: Nome da terapia (ex: "Brazilian Massage", "Reflexologia", "Massagem modeladora")
    
    Returns:
        Lista de terapias encontradas (sem domingo, sem duplicatas)
    """
    # Mapeamento de nomes de terapias para valores do parâmetro filtro
    mapeamento_filtro = {
        "massagem relaxante": "relaxante",
        "brazilian massage": "brazilian",
        "shiatsu": "shiatsu",
        "massagem ayurvédica": "ayurvedica",
        "reflexologia": "reflexologia",
        "indian head": "indian head",
        "spa relax": "day spa",
        "mini day spa": "mini day spa",
        "experiência beauty & relax": "casal",
        "drenagem corporal": "drenagem",
        "massagem modeladora": "modeladora",
        "tratamentos faciais": "facial"
    }
    
    nome_normalizado = nome_terapia.lower().strip()
    filtro = mapeamento_filtro.get(nome_normalizado, nome_normalizado)
    
    print(f"🔍 Buscando variações para: '{nome_terapia}'")
    print(f"   Parâmetro filtro: '{filtro}'")
    
    url = f'https://app.bellesoftware.com.br/api/release/controller/IntegracaoExterna/v1.0/servico/listar?codPlano=&codProf=&codSala=&filtro={filtro}&codCategoria=&codTipo='
    
    headers = {
        'Authorization': os.getenv("LABELLE_TOKEN")
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        todas_terapias = response.json()
    except Exception as e:
        print(f"❌ Erro ao buscar terapias da API: {e}")
        return []
    
    # Filtrar variações: remover "Dom" e agrupar duplicatas
    variacoes_unicas = {}
    
    for t in todas_terapias:
        nome_api = t.get("nome", "")
        
        # Pular variações de domingo
        if " Dom" in nome_api or " dom" in nome_api:
            continue
        
        # Usar nome base como chave (sem "Dom") para evitar duplicatas
        nome_base = nome_api.replace(" Dom", "").replace(" dom", "").strip()
        
        # Se já existe uma variação com esse nome base, manter apenas uma
        if nome_base not in variacoes_unicas:
            variacoes_unicas[nome_base] = t
    
    # Converter de volta para lista e ordenar por tempo
    variacoes = list(variacoes_unicas.values())
    variacoes.sort(key=lambda x: x.get("tempo", 0))
    
    print(f"✅ Encontradas {len(variacoes)} variações (após filtrar duplicatas e 'Dom')")
    for v in variacoes:
        print(f"   - {v.get('nome')} ({v.get('tempo')} min) - R$ {v.get('valor')}")
    
    return variacoes

# ============================================================================
# TOOLS PARA EXPLICAÇÃO DE TERAPIAS
# ============================================================================

async def explicar_terapia(ctx: RunContext[MyDeps], nome_terapia: str) -> str:
    """
    Apresenta explicação sobre uma terapia específica + opções de duração disponíveis.
    
    Args:
        ctx: Contexto da execução
        nome_terapia: Nome da terapia escolhida pelo usuário
    
    Returns:
        Explicação da terapia + opções de duração NUMERADAS
    """
    conversation_id = ctx.deps.session_id
    
    print("=" * 80)
    print("🔍 TOOL: explicar_terapia")
    print(f"Terapia solicitada: {nome_terapia}")
    print(f"Conversation ID: {conversation_id}")
    print("=" * 80)
    
    explicacao = _get_explicacao_terapia(nome_terapia)
    variacoes = _buscar_variacoes_terapia(nome_terapia)
    
    print(f"📊 Variações encontradas: {len(variacoes)}")
    for v in variacoes:
        print(f"   - {v.get('nome')} ({v.get('tempo')} min) - R$ {v.get('valor')}")
    
    session = get_session(conversation_id)
    if session:
        context = session[2] if len(session) > 2 else {}
        if isinstance(context, str):
            try:
                context = json.loads(context) if context else {}
            except:
                context = {}
        
        # Armazena última terapia visualizada E as variações disponíveis
        context["ultima_terapia_visualizada"] = nome_terapia
        context["variacoes_terapia"] = variacoes  # Armazena para uso posterior
        update_context(conversation_id, context)
    
    if variacoes:
        opcoes_duracao = []
        for i, v in enumerate(variacoes, 1):
            tempo = v.get("tempo")
            nome_completo = v.get("nome")
            opcoes_duracao.append(f"{i}. {nome_completo} ({tempo} minutos)")
        
        lista_opcoes = "\n".join(opcoes_duracao)
        
        resposta = f"""{explicacao}

Essas são as opções disponíveis:
{lista_opcoes}

Qual opção você prefere?"""
    else:
        # Se não encontrou variações, informa erro e pede para tentar novamente
        resposta = f"""{explicacao}

⚠️ No momento não consegui carregar as opções de duração disponíveis para esta terapia.

Por favor, tente novamente em alguns instantes ou escolha outra terapia."""
    
    print(f"✅ Explicação retornada para: {nome_terapia}")
    print("=" * 80)
    
    return resposta

async def listar_outras_terapias(ctx: RunContext[MyDeps], categoria_macro: str, excluir_terapia: str = None) -> str:
    """
    Lista terapias de uma categoria, excluindo a já visualizada.
    
    Args:
        ctx: Contexto da execução
        categoria_macro: "Relaxamento corporal", "Experiências completas (Day Spa)", ou "Estética corporal e facial"
        excluir_terapia: Nome da terapia a ser excluída da lista
    
    Returns:
        Lista de terapias restantes da categoria
    """
    conversation_id = ctx.deps.session_id
    
    print("=" * 80)
    print("🔍 TOOL: listar_outras_terapias")
    print(f"Categoria: {categoria_macro}")
    print(f"Excluir: {excluir_terapia}")
    print(f"Conversation ID: {conversation_id}")
    print("=" * 80)
    
    terapias = TERAPIAS_POR_CATEGORIA.get(categoria_macro, [])
    
    if not terapias:
        return f"❌ Categoria '{categoria_macro}' não encontrada."
    
    if excluir_terapia:
        terapias_restantes = [t for t in terapias if t.lower() != excluir_terapia.lower()]
    else:
        terapias_restantes = terapias
    
    if not terapias_restantes:
        return "Você já visualizou todas as opções desta categoria. Deseja escolher alguma delas?"
    
    lista = "\n".join(terapias_restantes)
    
    resposta = f"""Essas são as outras opções disponíveis:
{lista}

Sobre qual delas você gostaria de saber mais? 😊"""
    
    print(f"✅ {len(terapias_restantes)} terapias restantes listadas")
    print("=" * 80)
    
    return resposta

# ============================================================================
# TOOLS PARA AGENDAMENTO
# ============================================================================

async def validar_data_prazo_30_dias(ctx: RunContext[MyDeps], data_texto: str) -> str:
    """
    Valida se a data informada pelo usuário está dentro do prazo de 30 dias.
    Usa resolver_data para interpretar a data e calcular se está no prazo.
    
    Args:
        data_texto: Data informada pelo usuário (pode ser "amanhã", "próxima sexta", "25/03/2026", etc.)
    
    Returns:
        Mensagem de validação com a data formatada ou erro se fora do prazo
    """
    print("=" * 80)
    print(f"🔍 TOOL: validar_data_prazo_30_dias")
    print(f"Data informada: {data_texto}")
    print(f"Conversation ID: {ctx.deps.session_id}")
    print("=" * 80)
    
    # Usa resolver_data para interpretar a data
    agora = datetime.now(tz=TZ_BR)
    resultado = utils.resolver_data(data_texto, agora)
    
    if not resultado["ok"]:
        return f"""❌ {resultado['motivo']}

Por favor, informe a data no formato DD/MM/AAAA ou use termos como "amanhã", "próxima segunda", etc."""
    
    # Converte a data para objeto date para calcular diferença
    data_str = resultado["data"]  # formato DD/MM/AAAA
    dia_semana = resultado["dia_semana"]
    
    try:
        data_obj = datetime.strptime(data_str, "%d/%m/%Y").date()
    except ValueError:
        return "❌ Erro ao processar a data. Por favor, tente novamente."
    
    # Calcula diferença em dias
    hoje = agora.date()
    diferenca_dias = (data_obj - hoje).days
    
    print(f"📅 Data interpretada: {data_str} ({dia_semana})")
    print(f"📊 Diferença em dias: {diferenca_dias}")
    
    # Verifica se está dentro de 30 dias
    if diferenca_dias < 0:
        return f"""❌ A data {data_str} ({dia_semana}) já passou.

Por favor, informe uma data futura."""
    
    if diferenca_dias > 30:
        limite = (hoje + timedelta(days=30)).strftime("%d/%m/%Y")
        
        # Armazena que a data está fora do prazo (não armazena a data)
        update_context(ctx.deps.session_id, {
            "data_agendamento": None,
            "periodo": None
        })
        
        print(f"⚠️ Data fora do prazo de 30 dias")
        print("=" * 80)
        
        return f"""⚠️ Os agendamentos estão disponíveis apenas para os próximos 30 dias (até {limite}).

Para datas posteriores, é necessário entrar em contato diretamente com a unidade:

📞 **Telefone:** (11) 3796-7799
📱 **WhatsApp:** (11) 97348-5060

Gostaria de informar uma nova data?"""
    
    # Data válida - armazena no contexto
    update_context(ctx.deps.session_id, {
        "data_agendamento": data_str,
        "dia_semana": dia_semana
    })
    
    print(f"✅ Data válida e armazenada: {data_str} ({dia_semana})")
    print("=" * 80)
    
    return f"""✅ Perfeito! Agendamento para {dia_semana}, {data_str}.

Qual período você prefere? (manhã, tarde ou noite)"""

async def armazenar_periodo(ctx: RunContext[MyDeps], periodo_texto: str) -> str:
    """
    Valida e armazena o período escolhido pelo usuário (manhã, tarde ou noite).
    
    Args:
        periodo_texto: Período informado pelo usuário
    
    Returns:
        Confirmação do período armazenado
    """
    print("=" * 80)
    print(f"🔍 TOOL: armazenar_periodo")
    print(f"Período informado: {periodo_texto}")
    print(f"Conversation ID: {ctx.deps.session_id}")
    print("=" * 80)
    
    # Normaliza o texto
    periodo_normalizado = periodo_texto.lower().strip()
    
    # Remove acentos
    periodo_normalizado = (periodo_normalizado
        .replace("ã", "a")
        .replace("manhã", "manha")
    )
    
    # Mapeia variações para os valores aceitos
    mapeamento_periodo = {
        "manha": "manha",
        "manhã": "manha",
        "de manha": "manha",
        "pela manha": "manha",
        "tarde": "tarde",
        "a tarde": "tarde",
        "pela tarde": "tarde",
        "noite": "noite",
        "a noite": "noite",
        "pela noite": "noite",
        "de noite": "noite",
    }
    
    periodo_valido = None
    for variacao, valor in mapeamento_periodo.items():
        if variacao in periodo_normalizado:
            periodo_valido = valor
            break
    
    if not periodo_valido:
        return """❌ Período inválido.

Por favor, escolha entre: **manhã**, **tarde** ou **noite**."""
    
    # Armazena no contexto
    update_context(ctx.deps.session_id, {
        "periodo": periodo_valido
    })
    
    # Formata para exibição
    periodo_display = {
        "manha": "manhã",
        "tarde": "tarde",
        "noite": "noite"
    }[periodo_valido]
    
    print(f"✅ Período válido e armazenado: {periodo_valido}")
    print("=" * 80)
    
    return f"✅ Período escolhido: {periodo_display}."

@Tool
async def validar_variacao_terapia_vale(
    ctx: RunContext[MyDeps],
    escolha_usuario: str
) -> str:
    """
    Valida a escolha de uma variação específica de terapia (quando há múltiplas opções)
    e verifica se o vale bem-estar cobre o valor.
    
    Esta tool deve ser usada quando:
    - O usuário já viu uma lista de variações (ex: Ayurvedica 60 e 90)
    - O usuário escolheu uma opção (por número ou nome)
    - Precisa validar se o vale cobre essa escolha específica
    
    Args:
        escolha_usuario: Escolha do usuário (número da lista ou nome da terapia)
    
    Returns:
        Mensagem indicando se o vale cobre e se pode prosseguir
    """
    conversation_id = ctx.deps.session_id
    
    print("=" * 80)
    print("🔍 TOOL: validar_variacao_terapia_vale")
    print(f"Conversation ID: {conversation_id}")
    print(f"Escolha do usuário: {escolha_usuario}")
    print("=" * 80)
    
    # Busca as variações armazenadas no contexto
    session = get_session(conversation_id)
    context = session[2] if session else {}
    
    if isinstance(context, str):
        try:
            context = json.loads(context) if context else {}
        except:
            context = {}
    
    variacoes = context.get('variacoes_terapia', [])
    
    if not variacoes:
        print("❌ Nenhuma variação encontrada no contexto")
        return "❌ Erro: não encontrei as opções de terapia. Por favor, informe novamente qual terapia deseja."
    
    print(f"✅ Variações disponíveis no contexto: {len(variacoes)}")
    for i, v in enumerate(variacoes, 1):
        print(f"   {i}. {v.get('nome')} - R$ {v.get('valor')}")
    
    # Identifica qual variação o usuário escolheu
    terapia_escolhida = None
    escolha_normalizada = escolha_usuario.strip().lower()
    
    # Tenta interpretar como número
    if escolha_normalizada.isdigit():
        indice = int(escolha_normalizada) - 1
        if 0 <= indice < len(variacoes):
            terapia_escolhida = variacoes[indice]
            print(f"✅ Usuário escolheu opção {escolha_normalizada}: {terapia_escolhida.get('nome')}")
    
    # Se não for número, tenta match por nome
    if not terapia_escolhida:
        for v in variacoes:
            nome_v = v.get('nome', '').lower()
            if escolha_normalizada in nome_v or nome_v in escolha_normalizada:
                terapia_escolhida = v
                print(f"✅ Usuário escolheu por nome: {terapia_escolhida.get('nome')}")
                break
    
    if not terapia_escolhida:
        print("❌ Não foi possível identificar a escolha do usuário")
        return "❌ Não consegui identificar sua escolha. Por favor, informe o número da opção (1, 2, etc) ou o nome completo da terapia."
    
    # Extrai dados da terapia escolhida
    nome_terapia = terapia_escolhida.get('nome')
    codigo_servico = terapia_escolhida.get('codServico')
    valor_str = terapia_escolhida.get('valor', '0')
    
    # Converte valor (formato "188,00" -> 188.00)
    valor_str_convertido = str(valor_str).replace('.', '').replace(',', '.')
    try:
        valor_terapia = float(valor_str_convertido)
    except ValueError:
        print(f"❌ Erro ao converter valor: {valor_str}")
        valor_terapia = 0.0
    
    print(f"✅ Terapia selecionada: {nome_terapia}")
    print(f"   Código: {codigo_servico}")
    print(f"   Valor: R$ {valor_terapia:.2f}")
    
    # Pega tipo e valor do vale
    tipo_valor_vale = context.get('tipo_valor_vale', '')
    valor_vale_str = context.get('valor_vale', '0')
    
    print(f"   Tipo do vale: {tipo_valor_vale}")
    print(f"   Valor do vale (raw): {valor_vale_str}")
    
    # Armazena terapia escolhida no contexto
    context_update = {
        "terapia": nome_terapia,
        "codigo_servico": codigo_servico,
        "valor_terapia": valor_terapia
    }
    update_context(conversation_id, context_update)
    ctx.deps.terapia = nome_terapia
    
    print(f"✅ Terapia armazenada no contexto: {nome_terapia}")
    
    # VALE PERCENTUAL - Sempre cobre
    if "Percentual" in tipo_valor_vale or "%" in tipo_valor_vale:
        print("✅ Vale é PERCENTUAL - Sempre cobre")
        print("=" * 80)
        return f"""✅ Tudo certo! Seu vale bem-estar cobre essa experiência. 😉

<strong>Terapia:</strong> {nome_terapia}

Vamos prosseguir para a escolha da data do agendamento."""
    
    # VALE REAL - Compara valores
    valor_vale_convertido = str(valor_vale_str).replace('.', '').replace(',', '.')
    try:
        valor_vale = float(valor_vale_convertido)
    except:
        valor_vale = 0.0
    
    print(f"   Valor do vale (convertido): R$ {valor_vale:.2f}")
    print(f"   Valor da terapia: R$ {valor_terapia:.2f}")
    
    # Verifica se o vale cobre
    if valor_vale >= valor_terapia:
        print("✅ Vale COBRE o valor da terapia")
        print("=" * 80)
        return f"""✅ Tudo certo! Seu vale bem-estar cobre essa experiência. 😉

<strong>Terapia:</strong> {nome_terapia}

Vamos prosseguir para a escolha da data do agendamento."""
    else:
        print(f"⚠️ Vale NÃO COBRE o valor da terapia")
        print("=" * 80)
        return f"""⚠️ Essa terapia pode ser realizada com o seu vale, porém será necessário acertar uma diferença diretamente na unidade no dia do atendimento.

<strong>Terapia:</strong> {nome_terapia}

Deseja continuar mesmo assim?"""

@Tool
async def identificar_terapeuta_recorrente(
    ctx: RunContext[MyDeps],
    dtInicio: str,
    dtFim: str
) -> str:
    """
    Retorna o terapeuta mais recorrente no histórico do cliente.
    
    Só utilizar após o cliente escolher a terapia e informar a data desejada.
    Busca no histórico dos últimos 6 meses para identificar se há um terapeuta recorrente.
    
    Args:
        dtInicio: data inicial para busca no formato 'DD/MM/AAAA'
        dtFim: data final para busca no formato 'DD/MM/AAAA'
    
    Returns:
        str: JSON string com o terapeuta recorrente ou lista vazia
    """
    conversation_id = ctx.deps.session_id
    codigo_usuario = ctx.deps.codigo_usuario
    
    print("=" * 80)
    print("🔍 TOOL: identificar_terapeuta_recorrente")
    print(f"Conversation ID: {conversation_id}")
    print(f"Código usuário: {codigo_usuario}")
    print(f"Período: {dtInicio} até {dtFim}")
    print("=" * 80)
    
    url = (
        "https://app.bellesoftware.com.br/api/release/controller/"
        f"IntegracaoExterna/v1.0/cliente/agenda?codCliente={codigo_usuario}&codEstab=1&dtInicio={dtInicio}&dtFim={dtFim}"
    )
    
    headers = {
        "Authorization": os.getenv("LABELLE_TOKEN")
    }
    
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        
        agendas = response.json()
        print(f"Histórico bruto de agendas do cliente {codigo_usuario}: {len(agendas)} registros")
        
        contagem_terapeutas = {}
        nomes_terapeutas = {}
        
        for agenda in agendas:
            prof = agenda.get("prof") or {}
            
            # tenta várias chaves possíveis
            cod = (
                prof.get("cod")
                or prof.get("codProf")
                or prof.get("cod_usuario")
                or prof.get("codigo")
            )
            
            nome = (
                prof.get("nome")
                or prof.get("nom_usuario")
                or prof.get("nomeProf")
                or prof.get("usuario")
            )
            
            if not cod:
                continue
            
            cod = str(cod).strip()
            if not cod:
                continue
            
            contagem_terapeutas[cod] = contagem_terapeutas.get(cod, 0) + 1
            
            # só salva/atualiza nome se vier algo válido
            if nome and str(nome).strip():
                nomes_terapeutas[cod] = str(nome).strip()
        
        if not contagem_terapeutas:
            print("❌ Nenhum histórico encontrado")
            print("=" * 80)
            return json.dumps([], ensure_ascii=False)
        
        print(f"DEBUG HISTORICO - contagem_final={contagem_terapeutas}")
        print(f"DEBUG HISTORICO - nomes_finais={nomes_terapeutas}")
        
        cod_mais_frequente = max(contagem_terapeutas, key=contagem_terapeutas.get)
        quantidade = contagem_terapeutas[cod_mais_frequente]
        
        # regra mínima para considerar recorrente (pelo menos 3 atendimentos)
        if quantidade < 3:
            print(f"⚠️ Terapeuta mais frequente tem apenas {quantidade} atendimentos (mínimo: 3)")
            print("=" * 80)
            return json.dumps([], ensure_ascii=False)
        
        resultado = [{
            "nome": nomes_terapeutas.get(cod_mais_frequente, "Não identificado"),
            "codProf": cod_mais_frequente,
            "quantidade_atendimentos": quantidade
        }]
        
        print(
            f"DEBUG HISTORICO - terapeuta_mais_frequente={cod_mais_frequente} "
            f"nome={nomes_terapeutas.get(cod_mais_frequente, 'Não identificado')} "
            f"quantidade={quantidade}"
        )
        
        print(f"✅ Terapeuta recorrente identificado: {resultado}")
        print("=" * 80)
        return json.dumps(resultado, ensure_ascii=False)
    
    except Exception as e:
        print(f"❌ Erro ao consultar histórico de terapeutas: {e}")
        print("=" * 80)
        return json.dumps(
            {"erro": "Não foi possível consultar o histórico de terapeutas no momento"},
            ensure_ascii=False
        )

@Tool
async def verificar_terapeuta_faz_terapia(
    ctx: RunContext[MyDeps],
    codProf: str
) -> str:
    """
    Verifica se um terapeuta específico realiza a terapia escolhida pelo usuário.
    
    Consulta a API para verificar se o terapeuta está disponível para realizar
    a terapia na data e período escolhidos.
    
    Args:
        codProf: código do terapeuta a verificar
    
    Returns:
        str: "sim" se o terapeuta faz a terapia, "nao" caso contrário
    """
    conversation_id = ctx.deps.session_id
    
    # Busca dados do contexto
    session = get_session(conversation_id)
    context = session[2] if session else {}
    
    if isinstance(context, str):
        try:
            context = json.loads(context) if context else {}
        except:
            context = {}
    
    codigo_servico = context.get('codigo_servico')
    data_agendamento = context.get('data_agendamento')
    periodo = context.get('periodo')
    
    print("=" * 80)
    print("🔍 TOOL: verificar_terapeuta_faz_terapia")
    print(f"Conversation ID: {conversation_id}")
    print(f"Código terapeuta: {codProf}")
    print(f"Código serviço: {codigo_servico}")
    print(f"Data: {data_agendamento}")
    print(f"Período: {periodo}")
    print("=" * 80)
    
    if not codigo_servico or not data_agendamento or not periodo:
        print("❌ Dados insuficientes no contexto")
        print("=" * 80)
        return "erro"
    
    tpAgd = "p"
    url = f'https://app.bellesoftware.com.br/api/release/controller/IntegracaoExterna/v1.0/agenda/disponibilidade?codEstab=1&dtAgenda={data_agendamento}&periodo={periodo}&tpAgd={tpAgd}&servicos={codigo_servico}'
    
    headers = {
        'Authorization': os.getenv("LABELLE_TOKEN")
    }
    
    try:
        # Busca em múltiplas datas (próximos 7 dias) para verificar se o terapeuta REALIZA a terapia
        # Não apenas se tem horários disponíveis na data escolhida
        from datetime import datetime, timedelta
        
        data_obj = datetime.strptime(data_agendamento, '%d/%m/%Y')
        terapeuta_encontrado = False
        
        print(f"🔍 Buscando terapeuta {codProf} nos próximos 7 dias a partir de {data_agendamento}")
        
        for i in range(7):
            data_busca = (data_obj + timedelta(days=i)).strftime('%d/%m/%Y')
            url_busca = f'https://app.bellesoftware.com.br/api/release/controller/IntegracaoExterna/v1.0/agenda/disponibilidade?codEstab=1&dtAgenda={data_busca}&periodo=todos&tpAgd=p&servicos={codigo_servico}'
            
            response = requests.get(url_busca, headers=headers)
            response.raise_for_status()
            
            agendas = response.json()
            
            # Procura o terapeuta em qualquer data
            for agenda in agendas:
                horarios = agenda.get("horarios", [])
                
                for horario in horarios:
                    cod_prof_api = str(horario.get("codProf", "")).strip()
                    if cod_prof_api == str(codProf).strip():
                        nome_terapeuta = horario.get("nome", "")
                        print(f"✅ Terapeuta {nome_terapeuta} (cod: {codProf}) FAZ a terapia escolhida")
                        print(f"   Encontrado em {agenda.get('data')} com horários disponíveis")
                        print("=" * 80)
                        terapeuta_encontrado = True
                        return "sim"
            
            if terapeuta_encontrado:
                break
        
        # Se não encontrou em nenhuma das 7 datas, o terapeuta não faz essa terapia
        print(f"❌ Terapeuta {codProf} NÃO FAZ a terapia escolhida (não encontrado em 7 dias de busca)")
        print("=" * 80)
        return "nao"
    
    except Exception as e:
        print(f"❌ Erro ao verificar terapeuta: {e}")
        print("=" * 80)
        return "erro"

# ============================================================================
# TOOLS - SELEÇÃO DE TERAPEUTA
# ============================================================================

@Tool
def listar_terapeutas_disponiveis(ctx: RunContext[MyDeps]) -> str:
    """
    Retorna uma lista de terapeutas disponíveis no Buddha Spa.
    Esta ferramenta só deve ser chamada quando o usuário não tem terapeuta de preferência.
    
    Returns:
        str: Lista de nomes dos terapeutas separados por vírgula
    """
    conversation_id = ctx.deps.session_id
    
    print("=" * 80)
    print("🔍 TOOL: listar_terapeutas_disponiveis")
    print(f"Conversation ID: {conversation_id}")
    print("=" * 80)
    
    url = "https://app.bellesoftware.com.br/api/release/controller/IntegracaoExterna/v1.0/usuario/listar?codEstab=1&usuario&possuiAgenda=1"
    headers = {
        'Authorization': os.getenv("LABELLE_TOKEN")
    }
    
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        
        data = response.json()
        print(f"Total de terapeutas retornados: {len(data)}")
        
        if not data:
            print("⚠️ Nenhum terapeuta encontrado")
            return "Nenhum terapeuta disponível no momento."
        
        # Armazena lista completa de terapeutas no contexto para validação posterior
        terapeutas_completo = []
        primeiros_nomes = []
        
        for terapeuta in data:
            nome_completo = terapeuta.get("nom_usuario", "").strip()
            cod_prof = terapeuta.get("cod_usuario")
            
            if nome_completo and cod_prof:
                # Extrai apenas o primeiro nome
                primeiro_nome = nome_completo.split()[0] if nome_completo else nome_completo
                
                terapeutas_completo.append({
                    "nome": nome_completo,  # Armazena nome completo para validação
                    "codProf": str(cod_prof)
                })
                primeiros_nomes.append(primeiro_nome)
        
        # Armazena no contexto para uso posterior
        update_context(conversation_id, {
            "lista_terapeutas": terapeutas_completo
        })
        
        # Retorna lista numerada com apenas primeiros nomes
        lista_numerada = "\n".join([f"{i+1}. {nome}" for i, nome in enumerate(primeiros_nomes)])
        print(f"✅ Terapeutas encontrados (primeiros nomes): {', '.join(primeiros_nomes)}")
        print("=" * 80)
        
        return lista_numerada
    
    except Exception as e:
        print(f"❌ Erro ao listar terapeutas: {e}")
        print("=" * 80)
        return "Erro ao consultar terapeutas disponíveis."

@Tool
def validar_terapeuta_escolhido(ctx: RunContext[MyDeps], nome_terapeuta: str) -> str:
    """
    Valida se o terapeuta mencionado pelo usuário existe na lista de terapeutas disponíveis.
    
    Args:
        nome_terapeuta: Nome do terapeuta mencionado pelo usuário
    
    Returns:
        str: JSON com resultado da validação
    """
    conversation_id = ctx.deps.session_id
    
    print("=" * 80)
    print("🔍 TOOL: validar_terapeuta_escolhido")
    print(f"Conversation ID: {conversation_id}")
    print(f"Nome mencionado: {nome_terapeuta}")
    print("=" * 80)
    
    # Busca lista de terapeutas do contexto
    session = get_session(conversation_id)
    context = session[2] if session else {}
    
    if isinstance(context, str):
        try:
            context = json.loads(context) if context else {}
        except:
            context = {}
    
    lista_terapeutas = context.get('lista_terapeutas', [])
    
    if not lista_terapeutas:
        print("⚠️ Lista de terapeutas não encontrada no contexto")
        return "ERRO: Lista de terapeutas não disponível"
    
    # Normaliza nome para comparação (remove acentos, lowercase, etc)
    def normalizar_nome(nome):
        import unicodedata
        nome = nome.lower().strip()
        nome = unicodedata.normalize('NFD', nome)
        nome = ''.join(c for c in nome if unicodedata.category(c) != 'Mn')
        return nome
    
    nome_normalizado = normalizar_nome(nome_terapeuta)
    print(f"Nome normalizado do usuário: '{nome_normalizado}'")
    
    # Busca terapeuta
    melhor_match = None
    melhor_score = 0
    
    for terapeuta in lista_terapeutas:
        nome_lista = terapeuta.get("nome", "")
        nome_lista_normalizado = normalizar_nome(nome_lista)
        
        print(f"  Comparando com: '{nome_lista}' -> normalizado: '{nome_lista_normalizado}'")
        
        # Match exato
        if nome_normalizado == nome_lista_normalizado:
            print(f"    ✅ Match EXATO!")
            melhor_match = terapeuta
            melhor_score = 1.0
            break
        
        # Match parcial - verifica se o nome digitado está contido no nome completo
        # Ex: "joao" está em "joao todos segdomintegral"
        if nome_normalizado in nome_lista_normalizado:
            # Prioriza matches no início do nome
            palavras_lista = nome_lista_normalizado.split()
            score = 0.7  # Score base para match parcial
            
            # Se o nome digitado é igual à primeira palavra, aumenta score
            if palavras_lista and nome_normalizado == palavras_lista[0]:
                score = 0.9
                print(f"    ✅ Match PRIMEIRA PALAVRA! Score: {score}")
            else:
                print(f"    ✅ Match PARCIAL! Score: {score}")
            
            if score > melhor_score:
                melhor_match = terapeuta
                melhor_score = score
        else:
            print(f"    ❌ Sem match")
    
    if melhor_match and melhor_score > 0.5:
        print(f"✅ Terapeuta encontrado: {melhor_match['nome']} (cod: {melhor_match['codProf']}) - Score: {melhor_score}")
        
        # Armazena terapeuta escolhido no contexto
        update_context(conversation_id, {
            "terapeuta_escolhido": melhor_match['nome'],
            "terapeuta_codProf": melhor_match['codProf']
        })
        
        print("=" * 80)
        return f"ENCONTRADO|{melhor_match['nome']}|{melhor_match['codProf']}"
    else:
        print(f"❌ Terapeuta '{nome_terapeuta}' não encontrado")
        
        # Retorna sugestões
        sugestoes = [t['nome'] for t in lista_terapeutas[:5]]
        
        print("=" * 80)
        sugestoes_str = ", ".join(sugestoes)
        return f"NAO_ENCONTRADO|{sugestoes_str}"

@Tool
def verificar_terapeuta_realiza_terapia(
    ctx: RunContext[MyDeps],
    codProf: str,
    codigo_servico: str,
    dtAgenda: str,
    periodo: str
) -> str:
    """
    Verifica se um terapeuta específico realiza a terapia escolhida e retorna os horários disponíveis.
    
    Args:
        codProf: Código do terapeuta
        codigo_servico: Código do serviço/terapia
        dtAgenda: Data do agendamento no formato 'DD/MM/AAAA'
        periodo: Período do dia ('manha', 'tarde', 'noite' ou 'todos')
    
    Returns:
        str: JSON com resultado da verificação e horários disponíveis
    """
    conversation_id = ctx.deps.session_id
    
    print("=" * 80)
    print("🔍 TOOL: verificar_terapeuta_realiza_terapia")
    print(f"Conversation ID: {conversation_id}")
    print(f"Código terapeuta: {codProf}")
    print(f"Código serviço: {codigo_servico}")
    print(f"Data: {dtAgenda}")
    print(f"Período: {periodo}")
    print("=" * 80)
    
    url = f'https://app.bellesoftware.com.br/api/release/controller/IntegracaoExterna/v1.0/agenda/disponibilidade?codEstab=1&dtAgenda={dtAgenda}&periodo={periodo}&tpAgd=p&servicos={codigo_servico}'
    headers = {
        'Authorization': os.getenv("LABELLE_TOKEN")
    }
    
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        
        agendas = response.json()
        print(f"Agendas retornadas: {len(agendas)} dias")
        
        # Busca pela data específica
        for agenda in agendas:
            if agenda.get("data") == dtAgenda:
                horarios_dia = agenda.get("horarios", [])
                print(f"Horários encontrados para {dtAgenda}: {len(horarios_dia)} terapeutas")
                
                # Busca o terapeuta específico
                for terapeuta_agenda in horarios_dia:
                    cod_prof_api = str(terapeuta_agenda.get("codProf", "")).strip()
                    
                    if cod_prof_api == str(codProf).strip():
                        nome_terapeuta = terapeuta_agenda.get("nome", "")
                        horarios_disponiveis = terapeuta_agenda.get("horarios", [])
                        
                        print(f"✅ Terapeuta {nome_terapeuta} FAZ a terapia")
                        print(f"   Horários disponíveis: {len(horarios_disponiveis)}")
                        
                        # Formata horários no formato "09:00, 14:00, 16:30"
                        lista_horarios = ", ".join(horarios_disponiveis) if horarios_disponiveis else ""
                        
                        print("=" * 80)
                        return f"FAZ_TERAPIA|{lista_horarios}|{len(horarios_disponiveis)}"
                
                # Terapeuta não encontrado na lista = não faz a terapia
                print(f"❌ Terapeuta {codProf} NÃO FAZ a terapia escolhida")
                print("=" * 80)
                return "NAO_FAZ_TERAPIA||0"
        
        # Data não encontrada
        print(f"❌ Data {dtAgenda} não encontrada na agenda")
        print("=" * 80)
        return "NAO_FAZ_TERAPIA||0"
    
    except Exception as e:
        print(f"❌ Erro ao verificar terapeuta: {e}")
        print("=" * 80)
        return "ERRO||0"

@Tool
def buscar_proxima_data_disponivel_terapeuta(
    ctx: RunContext[MyDeps],
    codProf: str,
    codigo_servico: str,
    data_inicial: str,
    dias_busca: int = 5
) -> str:
    """
    Busca a próxima data disponível para um terapeuta específico nos próximos N dias.
    
    Args:
        codProf: Código do terapeuta
        codigo_servico: Código do serviço/terapia
        data_inicial: Data inicial para busca no formato 'DD/MM/AAAA'
        dias_busca: Quantidade de dias para buscar à frente (padrão: 5)
    
    Returns:
        str: JSON com resultado da busca
    """
    conversation_id = ctx.deps.session_id
    
    print("=" * 80)
    print("🔍 TOOL: buscar_proxima_data_disponivel_terapeuta")
    print(f"Conversation ID: {conversation_id}")
    print(f"Código terapeuta: {codProf}")
    print(f"Código serviço: {codigo_servico}")
    print(f"Data inicial: {data_inicial}")
    print(f"Dias de busca: {dias_busca}")
    print("=" * 80)
    
    try:
        # Converte data inicial para datetime
        from datetime import datetime, timedelta
        dt_inicial = datetime.strptime(data_inicial, '%d/%m/%Y')
        
        # Busca nos próximos N dias
        for i in range(1, dias_busca + 1):
            dt_busca = dt_inicial + timedelta(days=i)
            data_busca = dt_busca.strftime('%d/%m/%Y')
            dia_semana_num = dt_busca.weekday()
            dias_semana = ['segunda-feira', 'terça-feira', 'quarta-feira', 'quinta-feira', 'sexta-feira', 'sábado', 'domingo']
            dia_semana = dias_semana[dia_semana_num]
            
            print(f"Buscando em {data_busca} ({dia_semana})...")
            
            # Consulta disponibilidade para essa data
            url = f'https://app.bellesoftware.com.br/api/release/controller/IntegracaoExterna/v1.0/agenda/disponibilidade?codEstab=1&dtAgenda={data_busca}&periodo=todos&tpAgd=p&servicos={codigo_servico}'
            headers = {
                'Authorization': os.getenv("LABELLE_TOKEN")
            }
            
            response = requests.get(url, headers=headers)
            response.raise_for_status()
            
            agendas = response.json()
            
            # Busca pela data específica
            for agenda in agendas:
                if agenda.get("data") == data_busca:
                    horarios_dia = agenda.get("horarios", [])
                    
                    # Busca o terapeuta específico
                    for terapeuta_agenda in horarios_dia:
                        cod_prof_api = str(terapeuta_agenda.get("codProf", "")).strip()
                        
                        if cod_prof_api == str(codProf).strip():
                            horarios_disponiveis = terapeuta_agenda.get("horarios", [])
                            
                            if horarios_disponiveis:
                                lista_horarios = ", ".join(horarios_disponiveis)
                                
                                print(f"✅ Data disponível encontrada: {data_busca} ({dia_semana})")
                                print(f"   Horários: {lista_horarios}")
                                print("=" * 80)
                                
                                return f"ENCONTRADO|{data_busca}|{dia_semana}|{lista_horarios}|{len(horarios_disponiveis)}"
        
        # Não encontrou disponibilidade
        print(f"❌ Nenhuma data disponível encontrada nos próximos {dias_busca} dias")
        print("=" * 80)
        return "NAO_ENCONTRADO"
    
    except Exception as e:
        print(f"❌ Erro ao buscar próxima data: {e}")
        print("=" * 80)
        return "ERRO"

@Tool
def listar_horarios_terapeuta(
    ctx: RunContext[MyDeps],
    codProf: str,
    dtAgenda: str,
    periodo: str
) -> str:
    """
    Lista os horários disponíveis de um terapeuta específico para uma data e período.
    
    Args:
        codProf: Código do terapeuta
        dtAgenda: Data do agendamento no formato 'DD/MM/AAAA'
        periodo: Período do dia ('manha', 'tarde', 'noite' ou 'todos')
    
    Returns:
        str: Horários disponíveis no formato "09:00, 14:00, 16:30"
    """
    conversation_id = ctx.deps.session_id
    
    print("=" * 80)
    print("🔍 TOOL: listar_horarios_terapeuta")
    print(f"Conversation ID: {conversation_id}")
    print(f"Código terapeuta: {codProf}")
    print(f"Data: {dtAgenda}")
    print(f"Período: {periodo}")
    print("=" * 80)
    
    url = f'https://app.bellesoftware.com.br/api/release/controller/IntegracaoExterna/v1.0/agenda/disponibilidade?codEstab=1&dtAgenda={dtAgenda}&periodo={periodo}&tpAgd=p'
    headers = {
        'Authorization': os.getenv("LABELLE_TOKEN")
    }
    
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        
        agendas = response.json()
        print(f"Agendas retornadas: {len(agendas)} dias")
        
        # Busca pela data específica
        for agenda in agendas:
            if agenda.get("data") == dtAgenda:
                horarios_dia = agenda.get("horarios", [])
                print(f"Horários encontrados para {dtAgenda}: {len(horarios_dia)} terapeutas")
                
                # Busca o terapeuta específico
                for terapeuta_agenda in horarios_dia:
                    cod_prof_api = str(terapeuta_agenda.get("codProf", "")).strip()
                    
                    if cod_prof_api == str(codProf).strip():
                        nome_terapeuta = terapeuta_agenda.get("nome", "")
                        horarios_disponiveis = terapeuta_agenda.get("horarios", [])
                        
                        if horarios_disponiveis:
                            lista_horarios = ", ".join(horarios_disponiveis)
                            print(f"✅ Horários encontrados para {nome_terapeuta}: {lista_horarios}")
                            print("=" * 80)
                            return lista_horarios
                        else:
                            print(f"⚠️ Terapeuta {nome_terapeuta} não possui horários disponíveis")
                            print("=" * 80)
                            return "Nenhum horário disponível"
                
                # Terapeuta não encontrado
                print(f"❌ Terapeuta {codProf} não encontrado na agenda")
                print("=" * 80)
                return "Terapeuta não disponível nesta data"
        
        # Data não encontrada
        print(f"❌ Data {dtAgenda} não encontrada na agenda")
        print("=" * 80)
        return "Data não disponível"
    
    except Exception as e:
        print(f"❌ Erro ao listar horários: {e}")
        print("=" * 80)
        return "Erro ao consultar horários disponíveis"

@Tool
async def buscar_horarios_terapeuta(
    ctx: RunContext[MyDeps],
    codProf: str
) -> str:
    """
    Busca os horários disponíveis de um terapeuta específico na data e período escolhidos.
    
    Args:
        codProf: código do terapeuta
    
    Returns:
        str: JSON com horários disponíveis ou mensagem de erro
    """
    conversation_id = ctx.deps.session_id
    
    # Busca dados do contexto
    session = get_session(conversation_id)
    context = session[2] if session else {}
    
    if isinstance(context, str):
        try:
            context = json.loads(context) if context else {}
        except:
            context = {}
    
    codigo_servico = context.get('codigo_servico')
    data_agendamento = context.get('data_agendamento')
    periodo = context.get('periodo')
    
    print("=" * 80)
    print("🔍 TOOL: buscar_horarios_terapeuta")
    print(f"Conversation ID: {conversation_id}")
    print(f"Código terapeuta: {codProf}")
    print(f"Código serviço: {codigo_servico}")
    print(f"Data: {data_agendamento}")
    print(f"Período: {periodo}")
    print("=" * 80)
    
    if not codigo_servico or not data_agendamento or not periodo:
        print("❌ Dados insuficientes no contexto")
        print("=" * 80)
        return "ERRO|Dados insuficientes"
    
    # IMPORTANTE: Usar periodo=todos para garantir que retorne TODOS os terapeutas do dia
    # A API filtra terapeutas por período, então precisamos buscar todos e filtrar depois
    url = f'https://app.bellesoftware.com.br/api/release/controller/IntegracaoExterna/v1.0/agenda/disponibilidade?codEstab=1&dtAgenda={data_agendamento}&periodo=todos&tpAgd=p&servicos={codigo_servico}'
    
    headers = {
        'Authorization': os.getenv("LABELLE_TOKEN")
    }
    
    try:
        print(f"🌐 URL da API: {url}")
        print(f"⚠️ Buscando com periodo=todos (período escolhido pelo usuário: {periodo})")
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        
        agendas = response.json()
        
        print(f"📊 Total de agendas retornadas: {len(agendas)}")
        
        # Procura o terapeuta específico APENAS na data escolhida
        horarios_encontrados = []
        agenda_encontrada = False
        
        for idx, agenda in enumerate(agendas):
            data_agenda = agenda.get('data', '')
            print(f"\n📅 DEBUG - Agenda {idx}:")
            print(f"  Data: {data_agenda}")
            print(f"  Nome: {agenda.get('nome')}")
            print(f"  Disp: {agenda.get('disp')}")
            print(f"  Buscando data: {data_agendamento}")
            print(f"  Match de data: {data_agenda == data_agendamento}")
            
            # FILTRO CRÍTICO: Apenas processa a agenda da data escolhida
            if data_agenda != data_agendamento:
                print(f"  ⏭️ Pulando - data diferente da escolhida")
                continue
            
            agenda_encontrada = True
            horarios = agenda.get("horarios", [])
            print(f"  ✅ Data correta! Total de profissionais nesta agenda: {len(horarios)}")
            
            # Variáveis para armazenar dados do terapeuta encontrado
            nome_terapeuta_encontrado = ""
            intervalo_terapeuta = 10  # Padrão
            
            for prof_idx, horario in enumerate(horarios):
                cod_prof_api = str(horario.get("codProf", "")).strip()
                nome_prof = horario.get("nome", "")
                
                if cod_prof_api == str(codProf).strip():
                    print(f"  ✅ Terapeuta encontrado: {nome_prof} (cod: {cod_prof_api})")
                    nome_terapeuta_encontrado = nome_prof  # Armazena o nome
                    
                    # 🆕 CAPTURA INTERVALO DA API
                    tempo_intervalo_api = horario.get("tempo_intervalo", "10")
                    intervalo_terapeuta = int(tempo_intervalo_api)
                    print(f"  ⏱️ Intervalo do terapeuta (da API): {intervalo_terapeuta} min")
                    
                    # Verifica estrutura dos horários
                    horarios_prof = horario.get("horarios", [])
                    
                    # Tenta extrair horários de diferentes formas
                    if isinstance(horarios_prof, list):
                        for h in horarios_prof:
                            if isinstance(h, dict):
                                # Formato: [{"horario": "14:00"}, ...]
                                hora = h.get("horario", h.get("hora", ""))
                            else:
                                # Formato: ["14:00", "14:30", ...]
                                hora = str(h)
                            
                            if hora:
                                horarios_encontrados.append(hora)
                    
                    # Também verifica campo "hora" direto
                    hora_direta = horario.get("hora", "")
                    if hora_direta and hora_direta not in horarios_encontrados:
                        horarios_encontrados.append(hora_direta)
                    
                    print(f"  📋 Total de horários extraídos: {len(horarios_encontrados)}")
                    
                    # Filtrar horários por período escolhido
                    horarios_filtrados = []
                    for h in horarios_encontrados:
                        try:
                            # Extrai hora do formato "HH:MM"
                            hora_int = int(h.split(':')[0])
                            
                            # Define faixas de horário por período
                            if periodo == "manha" and 6 <= hora_int < 12:
                                horarios_filtrados.append(h)
                            elif periodo == "tarde" and 12 <= hora_int < 18:
                                horarios_filtrados.append(h)
                            elif periodo == "noite" and 18 <= hora_int < 24:
                                horarios_filtrados.append(h)
                        except:
                            # Se houver erro ao parsear, mantém o horário
                            horarios_filtrados.append(h)
                    
                    horarios_encontrados = horarios_filtrados
                    print(f"  🔍 Horários filtrados por período '{periodo}': {len(horarios_encontrados)}")
                    
                    # Encontrou o terapeuta, não precisa continuar
                    break
            
            # Encontrou a data, não precisa continuar
            break
        
        if not agenda_encontrada:
            print(f"❌ Data {data_agendamento} não encontrada nas agendas retornadas")
            print("=" * 80)
            return "SEM_HORARIOS||0"
        
        if horarios_encontrados:
            # 🔥 VALIDAÇÃO CRÍTICA: Considera duração da terapia + 10 min de intervalo
            # Busca duração da terapia no contexto
            duracao_terapia = None
            
            # Tenta extrair duração de variacoes_terapia
            variacoes = context.get('variacoes_terapia', [])
            terapia_escolhida = context.get('terapia', '')
            
            if variacoes:
                for v in variacoes:
                    if v.get('nome') == terapia_escolhida:
                        duracao_terapia = v.get('tempo')
                        print(f"  ⏱️ Duração da terapia encontrada em variações: {duracao_terapia} min")
                        break
            
            # Se não encontrou em variações, tenta extrair do nome da terapia (ex: "Ayurvedica 60")
            if not duracao_terapia and terapia_escolhida:
                import re
                match = re.search(r'\b(\d+)\b', terapia_escolhida)
                if match:
                    duracao_terapia = int(match.group(1))
                    print(f"  ⏱️ Duração da terapia extraída do nome: {duracao_terapia} min")
            
            # Se ainda não encontrou, usa duração padrão de 60 min
            if not duracao_terapia:
                duracao_terapia = 60
                print(f"  ⚠️ Duração não encontrada, usando padrão: {duracao_terapia} min")
            
            # 🆕 BUSCA DISPONIBILIDADE DE SALAS
            salas_disponiveis = _buscar_disponibilidade_salas(
                data_agendamento=data_agendamento,
                periodo=periodo,
                codigo_servico=codigo_servico
            )
            
            # 🆕 CRUZA HORÁRIOS TERAPEUTA X SALA
            horarios_validos, codSala, nome_sala, intervalo_sala = _cruzar_horarios_terapeuta_e_sala(
                horarios_terapeuta=horarios_encontrados,
                intervalo_terapeuta=intervalo_terapeuta,
                salas_disponiveis=salas_disponiveis,
                duracao_terapia=duracao_terapia
            )
            
            if horarios_validos:
                # Armazena horários VÁLIDOS e dados da sala no contexto
                update_context(conversation_id, {
                    "horarios_disponiveis": horarios_validos,
                    "terapeuta_codProf": codProf,
                    "terapeuta_escolhido": nome_terapeuta_encontrado,
                    "codSala": codSala,  # 🆕 Código da sala
                    "nome_sala": nome_sala  # 🆕 Nome da sala
                })
                
                horarios_str = ", ".join(horarios_validos)
                print(f"✅ Horários VÁLIDOS (terapeuta + sala): {len(horarios_validos)} horários")
                print(f"   Horários: {horarios_str}")
                print(f"   Sala: {nome_sala} (cod: {codSala})")
                print("=" * 80)
                return f"TEM_HORARIOS|{horarios_str}|{len(horarios_validos)}"
            else:
                print(f"❌ Nenhum horário válido após validação de duração + intervalo")
                print("=" * 80)
                return "SEM_HORARIOS||0"
        else:
            print(f"❌ Terapeuta {codProf} não tem horários disponíveis na data {data_agendamento} período {periodo}")
            print("=" * 80)
            return "SEM_HORARIOS||0"
    
    except Exception as e:
        print(f"❌ Erro ao buscar horários: {e}")
        print("=" * 80)
        return "ERRO|Erro ao consultar API"

@Tool
def validar_horario_escolhido(
    ctx: RunContext[MyDeps],
    horario_mencionado: str
) -> str:
    """
    Valida se o horário mencionado pelo usuário está na lista de horários disponíveis.
    
    Args:
        horario_mencionado: horário mencionado pelo usuário (ex: "14:00", "2 da tarde")
    
    Returns:
        str: "VALIDO|HH:MM" se válido, "INVALIDO" se não encontrado, "NENHUM" se usuário recusou todos
    """
    conversation_id = ctx.deps.session_id
    
    session = get_session(conversation_id)
    context = session[2] if session else {}
    
    if isinstance(context, str):
        try:
            context = json.loads(context) if context else {}
        except:
            context = {}
    
    horarios_disponiveis = context.get('horarios_disponiveis', [])
    
    print("=" * 80)
    print("🔍 TOOL: validar_horario_escolhido")
    print(f"Conversation ID: {conversation_id}")
    print(f"Horário mencionado: {horario_mencionado}")
    print(f"Horários disponíveis: {horarios_disponiveis}")
    print("=" * 80)
    
    if not horarios_disponiveis:
        print("❌ Lista de horários não encontrada no contexto")
        print("=" * 80)
        return "ERRO|Lista de horários não disponível"
    
    # Normaliza entrada do usuário
    horario_normalizado = horario_mencionado.lower().strip()
    
    # Verifica se usuário recusou todos os horários
    recusas = ["nenhum", "nenhuma", "nao quero", "não quero", "outro", "outra"]
    if any(recusa in horario_normalizado for recusa in recusas):
        print("❌ Usuário recusou todos os horários")
        print("=" * 80)
        return "NENHUM"
    
    # Tenta encontrar o horário na lista
    for horario_disponivel in horarios_disponiveis:
        # Remove caracteres especiais e compara
        horario_limpo = horario_disponivel.replace(":", "").strip()
        entrada_limpa = horario_normalizado.replace(":", "").replace("h", "").strip()
        
        # Match exato ou parcial
        if entrada_limpa in horario_limpo or horario_limpo in entrada_limpa:
            print(f"✅ Horário válido: {horario_disponivel}")
            
            # Armazena horário escolhido
            update_context(conversation_id, {
                "horario_escolhido": horario_disponivel
            })
            
            print("=" * 80)
            return f"VALIDO|{horario_disponivel}"
    
    print(f"❌ Horário '{horario_mencionado}' não encontrado na lista")
    print("=" * 80)
    return "INVALIDO"

@Tool
async def buscar_proximas_datas_disponiveis(
    ctx: RunContext[MyDeps],
    codProf: str
) -> str:
    """
    Busca as próximas 5 datas com horários disponíveis para o terapeuta.
    
    Args:
        codProf: código do terapeuta
    
    Returns:
        str: Lista de datas disponíveis separadas por vírgula ou mensagem de erro
    """
    conversation_id = ctx.deps.session_id
    
    session = get_session(conversation_id)
    context = session[2] if session else {}
    
    if isinstance(context, str):
        try:
            context = json.loads(context) if context else {}
        except:
            context = {}
    
    codigo_servico = context.get('codigo_servico')
    periodo = context.get('periodo')
    data_agendamento = context.get('data_agendamento')
    
    print("=" * 80)
    print("🔍 TOOL: buscar_proximas_datas_disponiveis")
    print(f"Conversation ID: {conversation_id}")
    print(f"Código terapeuta: {codProf}")
    print(f"Código serviço: {codigo_servico}")
    print(f"Data inicial: {data_agendamento}")
    print(f"Período: {periodo}")
    print("=" * 80)
    
    if not codigo_servico or not data_agendamento:
        print("❌ Dados insuficientes no contexto")
        print("=" * 80)
        return "ERRO|Dados insuficientes"
    
    from datetime import datetime, timedelta
    
    headers = {
        'Authorization': os.getenv("LABELLE_TOKEN")
    }
    
    try:
        data_obj = datetime.strptime(data_agendamento, '%d/%m/%Y')
        datas_com_horarios = []
        
        # Busca nos próximos 30 dias
        for i in range(1, 31):
            if len(datas_com_horarios) >= 5:
                break
            
            data_busca_obj = data_obj + timedelta(days=i)
            data_busca = data_busca_obj.strftime('%d/%m/%Y')
            dia_semana = data_busca_obj.strftime('%A')
            
            # Traduz dia da semana
            dias_pt = {
                'Monday': 'segunda-feira',
                'Tuesday': 'terça-feira',
                'Wednesday': 'quarta-feira',
                'Thursday': 'quinta-feira',
                'Friday': 'sexta-feira',
                'Saturday': 'sábado',
                'Sunday': 'domingo'
            }
            dia_semana_pt = dias_pt.get(dia_semana, dia_semana)
            
            url = f'https://app.bellesoftware.com.br/api/release/controller/IntegracaoExterna/v1.0/agenda/disponibilidade?codEstab=1&dtAgenda={data_busca}&periodo=todos&tpAgd=p&servicos={codigo_servico}'
            
            response = requests.get(url, headers=headers)
            response.raise_for_status()
            
            agendas = response.json()
            
            # Verifica se terapeuta tem horários nesta data E no período escolhido
            tem_horarios = False
            for agenda in agendas:
                # Verifica se é a data correta
                data_agenda = agenda.get("data", "")
                if data_agenda != data_busca:
                    continue
                
                horarios = agenda.get("horarios", [])
                for horario in horarios:
                    cod_prof_api = str(horario.get("codProf", "")).strip()
                    if cod_prof_api == str(codProf).strip():
                        # Extrai horários disponíveis do terapeuta
                        horarios_prof = horario.get("horarios", [])
                        horarios_encontrados = []
                        
                        if isinstance(horarios_prof, list):
                            for h in horarios_prof:
                                if isinstance(h, dict):
                                    hora = h.get("horario", h.get("hora", ""))
                                else:
                                    hora = str(h)
                                if hora:
                                    horarios_encontrados.append(hora)
                        
                        # Também verifica campo "hora" direto
                        hora_direta = horario.get("hora", "")
                        if hora_direta and hora_direta not in horarios_encontrados:
                            horarios_encontrados.append(hora_direta)
                        
                        # Filtra horários por período escolhido
                        horarios_filtrados = []
                        for h in horarios_encontrados:
                            try:
                                hora_int = int(h.split(':')[0])
                                
                                if periodo == "manha" and 6 <= hora_int < 12:
                                    horarios_filtrados.append(h)
                                elif periodo == "tarde" and 12 <= hora_int < 18:
                                    horarios_filtrados.append(h)
                                elif periodo == "noite" and 18 <= hora_int < 24:
                                    horarios_filtrados.append(h)
                            except:
                                horarios_filtrados.append(h)
                        
                        # 🔥 VALIDAÇÃO CRÍTICA: Considera duração da terapia + 10 min de intervalo
                        if horarios_filtrados:
                            # Busca duração da terapia no contexto
                            duracao_terapia = None
                            
                            # Tenta extrair duração de variacoes_terapia
                            variacoes = context.get('variacoes_terapia', [])
                            terapia_escolhida = context.get('terapia', '')
                            
                            if variacoes:
                                for v in variacoes:
                                    if v.get('nome') == terapia_escolhida:
                                        duracao_terapia = v.get('tempo')
                                        break
                            
                            # Se não encontrou em variações, tenta extrair do nome da terapia
                            if not duracao_terapia and terapia_escolhida:
                                import re
                                match = re.search(r'\b(\d+)\b', terapia_escolhida)
                                if match:
                                    duracao_terapia = int(match.group(1))
                            
                            # Se ainda não encontrou, usa duração padrão de 60 min
                            if not duracao_terapia:
                                duracao_terapia = 60
                            
                            # Aplica validação de duração + intervalo
                            horarios_validos = validar_horarios_com_duracao(
                                horarios_disponiveis=horarios_filtrados,
                                duracao_terapia=duracao_terapia,
                                intervalo_minutos=10
                            )
                            
                            # Só considera se tiver horários VÁLIDOS após validação
                            if horarios_validos:
                                tem_horarios = True
                        break
                if tem_horarios:
                    break
            
            if tem_horarios:
                datas_com_horarios.append(f"{dia_semana_pt}, {data_busca}")
                print(f"✅ Data disponível: {dia_semana_pt}, {data_busca}")
        
        if datas_com_horarios:
            # Armazena datas no contexto
            update_context(conversation_id, {
                "datas_alternativas": datas_com_horarios
            })
            
            datas_str = "\n".join(datas_com_horarios)
            print(f"✅ Encontradas {len(datas_com_horarios)} datas com horários")
            print("=" * 80)
            return f"TEM_DATAS|{datas_str}|{len(datas_com_horarios)}"
        else:
            print("❌ Nenhuma data com horários encontrada nos próximos 30 dias")
            print("=" * 80)
            return "SEM_DATAS||0"
    
    except Exception as e:
        print(f"❌ Erro ao buscar próximas datas: {e}")
        print("=" * 80)
        return "ERRO|Erro ao consultar API"

@Tool
async def buscar_terapeuta_alternativo(
    ctx: RunContext[MyDeps]
) -> str:
    """
    Busca um terapeuta alternativo que realize a terapia escolhida quando o terapeuta
    selecionado pelo usuário não realiza essa terapia.
    
    Returns:
        str: Dados do terapeuta alternativo ou mensagem de erro
    """
    conversation_id = ctx.deps.session_id
    
    session = get_session(conversation_id)
    context = session[2] if session else {}
    
    if isinstance(context, str):
        try:
            context = json.loads(context) if context else {}
        except:
            context = {}
    
    codigo_servico = context.get('codigo_servico')
    data_agendamento = context.get('data_agendamento')
    periodo = context.get('periodo')
    terapeuta_escolhido_cod = context.get('terapeuta_codProf')
    
    print("=" * 80)
    print("🔍 TOOL: buscar_terapeuta_alternativo")
    print(f"Conversation ID: {conversation_id}")
    print(f"Código serviço: {codigo_servico}")
    print(f"Data: {data_agendamento}")
    print(f"Período: {periodo}")
    print(f"Terapeuta escolhido (excluir): {terapeuta_escolhido_cod}")
    print("=" * 80)
    
    if not codigo_servico or not data_agendamento or not periodo:
        print("❌ Dados insuficientes no contexto")
        print("=" * 80)
        return "ERRO|Dados insuficientes"
    
    url = f'https://app.bellesoftware.com.br/api/release/controller/IntegracaoExterna/v1.0/agenda/disponibilidade?codEstab=1&dtAgenda={data_agendamento}&periodo={periodo}&tpAgd=p&servicos={codigo_servico}'
    
    headers = {
        'Authorization': os.getenv("LABELLE_TOKEN")
    }
    
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        
        agendas = response.json()
        
        # Busca primeiro terapeuta diferente do escolhido que tenha horários
        for agenda in agendas:
            horarios = agenda.get("horarios", [])
            
            for horario in horarios:
                cod_prof_api = str(horario.get("codProf", "")).strip()
                
                # Pula o terapeuta que o usuário escolheu
                if cod_prof_api == str(terapeuta_escolhido_cod).strip():
                    continue
                
                nome_terapeuta = horario.get("nome", "")
                hora = horario.get("hora", "")
                
                if nome_terapeuta and hora:
                    # Busca todos os horários deste terapeuta
                    horarios_terapeuta = []
                    for h in horarios:
                        if str(h.get("codProf", "")).strip() == cod_prof_api:
                            horarios_terapeuta.append(h.get("hora", ""))
                    
                    # Armazena terapeuta alternativo no contexto
                    update_context(conversation_id, {
                        "terapeuta_alternativo_nome": nome_terapeuta,
                        "terapeuta_alternativo_cod": cod_prof_api,
                        "horarios_disponiveis": horarios_terapeuta,
                        "terapeuta_codProf": cod_prof_api  # Atualiza para o alternativo
                    })
                    
                    horarios_str = ", ".join(horarios_terapeuta)
                    print(f"✅ Terapeuta alternativo encontrado: {nome_terapeuta} (cod: {cod_prof_api})")
                    print(f"   Horários: {horarios_str}")
                    print("=" * 80)
                    return f"ENCONTRADO|{nome_terapeuta}|{horarios_str}"
        
        print("❌ Nenhum terapeuta alternativo com horários disponíveis")
        print("=" * 80)
        return "NAO_ENCONTRADO||0"
    
    except Exception as e:
        print(f"❌ Erro ao buscar terapeuta alternativo: {e}")
        print("=" * 80)
        return "ERRO|Erro ao consultar API"


@Tool
async def armazenar_sem_preferencia_terapeuta(
    ctx: RunContext[MyDeps]
) -> str:
    """
    Armazena no contexto que o usuário não tem preferência de terapeuta.
    Define terapeuta_escolhido como "sem_preferencia".
    
    Returns:
        str: "OK" quando armazenado com sucesso
    """
    conversation_id = ctx.deps.session_id
    
    print("=" * 80)
    print("🔍 TOOL: armazenar_sem_preferencia_terapeuta")
    print(f"Conversation ID: {conversation_id}")
    print("=" * 80)
    
    # Armazena "sem_preferencia" no contexto
    update_context(conversation_id, {
        "terapeuta_escolhido": "sem_preferencia"
    })
    
    print("✅ Armazenado: terapeuta_escolhido = 'sem_preferencia'")
    print("=" * 80)
    
    return "OK"


@Tool
async def buscar_horarios_disponiveis_sem_terapeuta(
    ctx: RunContext[MyDeps]
) -> str:
    """
    Busca horários disponíveis sem especificar terapeuta.
    Retorna todos os horários válidos na data e período escolhidos.
    
    Returns:
        str: "TEM_HORARIOS|horarios|quantidade" ou "SEM_HORARIOS||0"
    """
    conversation_id = ctx.deps.session_id
    
    session = get_session(conversation_id)
    context = session[2] if session else {}
    
    if isinstance(context, str):
        try:
            context = json.loads(context) if context else {}
        except:
            context = {}
    
    codigo_servico = context.get('codigo_servico')
    data_agendamento = context.get('data_agendamento')
    periodo = context.get('periodo')
    
    print("=" * 80)
    print("🔍 TOOL: buscar_horarios_disponiveis_sem_terapeuta")
    print(f"Conversation ID: {conversation_id}")
    print(f"Código serviço: {codigo_servico}")
    print(f"Data: {data_agendamento}")
    print(f"Período: {periodo}")
    print("=" * 80)
    
    if not codigo_servico or not data_agendamento or not periodo:
        print("❌ Dados insuficientes no contexto")
        print("=" * 80)
        return "SEM_HORARIOS||0"
    
    headers = {
        'Authorization': os.getenv("LABELLE_TOKEN")
    }
    
    try:
        url = f'https://app.bellesoftware.com.br/api/release/controller/IntegracaoExterna/v1.0/agenda/disponibilidade?codEstab=1&dtAgenda={data_agendamento}&periodo=todos&tpAgd=p&servicos={codigo_servico}'
        
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        
        agendas = response.json()
        print(f"📊 Total de agendas retornadas: {len(agendas)}")
        
        # Busca pela data escolhida e coleta dados de TODOS os terapeutas
        terapeutas_disponiveis = []
        
        for agenda in agendas:
            data_agenda = agenda.get("data", "")
            if data_agenda != data_agendamento:
                continue
            
            print(f"✅ Data correta encontrada: {data_agendamento}")
            
            horarios = agenda.get("horarios", [])
            for horario in horarios:
                cod_prof = str(horario.get("codProf", "")).strip()
                nome_prof = horario.get("nome", "")
                tempo_intervalo_api = horario.get("tempo_intervalo", "10")
                intervalo_terapeuta = int(tempo_intervalo_api)
                
                horarios_prof = horario.get("horarios", [])
                lista_horarios = []
                
                if isinstance(horarios_prof, list):
                    for h in horarios_prof:
                        if isinstance(h, dict):
                            hora = h.get("horario", h.get("hora", ""))
                        else:
                            hora = str(h)
                        if hora:
                            lista_horarios.append(hora)
                
                hora_direta = horario.get("hora", "")
                if hora_direta and hora_direta not in lista_horarios:
                    lista_horarios.append(hora_direta)
                
                if cod_prof and lista_horarios:
                    terapeutas_disponiveis.append({
                        'cod_prof': cod_prof,
                        'nome': nome_prof,
                        'horarios': lista_horarios,
                        'intervalo': intervalo_terapeuta
                    })
            
            break  # Encontrou a data, não precisa continuar
        
        if not terapeutas_disponiveis:
            print("❌ Nenhum terapeuta encontrado para a data")
            print("=" * 80)
            return "SEM_HORARIOS||0"
        
        print(f"📊 Total de terapeutas disponíveis: {len(terapeutas_disponiveis)}")
        
        # Filtra horários de cada terapeuta por período
        for terapeuta in terapeutas_disponiveis:
            horarios_filtrados = []
            for h in terapeuta['horarios']:
                try:
                    hora_int = int(h.split(':')[0])
                    
                    if periodo == "manha" and 6 <= hora_int < 12:
                        horarios_filtrados.append(h)
                    elif periodo == "tarde" and 12 <= hora_int < 18:
                        horarios_filtrados.append(h)
                    elif periodo == "noite" and 18 <= hora_int < 24:
                        horarios_filtrados.append(h)
                except:
                    horarios_filtrados.append(h)
            
            terapeuta['horarios'] = sorted(horarios_filtrados)
        
        # Extrai duração da terapia
        terapia_escolhida = context.get('terapia', '')
        duracao_terapia = None
        
        variacoes = context.get('variacoes_terapia', [])
        if variacoes:
            for v in variacoes:
                if v.get('nome') == terapia_escolhida:
                    duracao_terapia = v.get('tempo')
                    break
        
        if not duracao_terapia and terapia_escolhida:
            import re
            match = re.search(r'\b(\d+)\b', terapia_escolhida)
            if match:
                duracao_terapia = int(match.group(1))
        
        if not duracao_terapia:
            duracao_terapia = 60
        
        print(f"⏱️ Duração da terapia: {duracao_terapia} min")
        
        # 🆕 BUSCA DISPONIBILIDADE DE SALAS
        salas_disponiveis = _buscar_disponibilidade_salas(
            data_agendamento=data_agendamento,
            periodo=periodo,
            codigo_servico=codigo_servico
        )
        
        # 🆕 TESTA CADA TERAPEUTA COM AS SALAS
        melhor_combinacao = {
            'horarios': [],
            'cod_prof': None,
            'nome_prof': None,
            'codSala': None,
            'nome_sala': None
        }
        
        for terapeuta in terapeutas_disponiveis:
            if not terapeuta['horarios']:
                continue
            
            print(f"\n👨‍⚕️ Testando terapeuta: {terapeuta['nome']} (cod: {terapeuta['cod_prof']})")
            
            # Cruza horários deste terapeuta com salas
            horarios_validos, codSala, nome_sala, intervalo_sala = _cruzar_horarios_terapeuta_e_sala(
                horarios_terapeuta=terapeuta['horarios'],
                intervalo_terapeuta=terapeuta['intervalo'],
                salas_disponiveis=salas_disponiveis,
                duracao_terapia=duracao_terapia
            )
            
            # Se este terapeuta tem mais horários que o melhor até agora, usa ele
            if len(horarios_validos) > len(melhor_combinacao['horarios']):
                melhor_combinacao = {
                    'horarios': horarios_validos,
                    'cod_prof': terapeuta['cod_prof'],
                    'nome_prof': terapeuta['nome'],
                    'codSala': codSala,
                    'nome_sala': nome_sala
                }
                print(f"   🏆 Melhor combinação até agora: {len(horarios_validos)} horários")
        
        if melhor_combinacao['horarios']:
            # Armazena horários e dados da melhor combinação no contexto
            update_context(conversation_id, {
                "horarios_disponiveis": melhor_combinacao['horarios'],
                "terapeuta_codProf": melhor_combinacao['cod_prof'],
                "terapeuta_escolhido": melhor_combinacao['nome_prof'],
                "codSala": melhor_combinacao['codSala'],
                "nome_sala": melhor_combinacao['nome_sala']
            })
            
            horarios_str = ", ".join(melhor_combinacao['horarios'])
            print(f"\n✅ MELHOR COMBINAÇÃO ENCONTRADA:")
            print(f"   Terapeuta: {melhor_combinacao['nome_prof']} (cod: {melhor_combinacao['cod_prof']})")
            print(f"   Sala: {melhor_combinacao['nome_sala']} (cod: {melhor_combinacao['codSala']})")
            print(f"   Horários: {len(melhor_combinacao['horarios'])}")
            print(f"   {horarios_str}")
            print("=" * 80)
            return f"TEM_HORARIOS|{horarios_str}|{len(melhor_combinacao['horarios'])}"
        else:
            print("❌ Nenhum horário válido após validação")
            print("=" * 80)
            return "SEM_HORARIOS||0"
    
    except Exception as e:
        print(f"❌ Erro ao buscar horários: {e}")
        print("=" * 80)
        return "SEM_HORARIOS||0"


@Tool
async def buscar_proximas_datas_sem_terapeuta(
    ctx: RunContext[MyDeps]
) -> str:
    """
    Busca as próximas 5 datas com horários disponíveis SEM terapeuta de preferência.
    Usado quando não há horários na data escolhida e usuário não tem preferência de terapeuta.
    
    Returns:
        str: "TEM_DATAS|datas|quantidade" ou "SEM_DATAS||0"
    """
    conversation_id = ctx.deps.session_id
    
    session = get_session(conversation_id)
    context = session[2] if session else {}
    
    if isinstance(context, str):
        try:
            context = json.loads(context) if context else {}
        except:
            context = {}
    
    codigo_servico = context.get('codigo_servico')
    periodo = context.get('periodo')
    data_agendamento = context.get('data_agendamento')
    
    print("=" * 80)
    print("🔍 TOOL: buscar_proximas_datas_sem_terapeuta")
    print(f"Conversation ID: {conversation_id}")
    print(f"Código serviço: {codigo_servico}")
    print(f"Data inicial: {data_agendamento}")
    print(f"Período: {periodo}")
    print("=" * 80)
    
    if not codigo_servico or not data_agendamento or not periodo:
        print("❌ Dados insuficientes no contexto")
        print("=" * 80)
        return "SEM_DATAS||0"
    
    from datetime import datetime, timedelta
    
    headers = {
        'Authorization': os.getenv("LABELLE_TOKEN")
    }
    
    try:
        data_obj = datetime.strptime(data_agendamento, '%d/%m/%Y')
        datas_com_horarios = []
        
        # Busca nos próximos 30 dias
        for i in range(1, 31):
            if len(datas_com_horarios) >= 5:
                break
            
            data_busca_obj = data_obj + timedelta(days=i)
            data_busca = data_busca_obj.strftime('%d/%m/%Y')
            dia_semana = data_busca_obj.strftime('%A')
            
            # Traduz dia da semana
            dias_pt = {
                'Monday': 'segunda-feira',
                'Tuesday': 'terça-feira',
                'Wednesday': 'quarta-feira',
                'Thursday': 'quinta-feira',
                'Friday': 'sexta-feira',
                'Saturday': 'sábado',
                'Sunday': 'domingo'
            }
            dia_semana_pt = dias_pt.get(dia_semana, dia_semana)
            
            url = f'https://app.bellesoftware.com.br/api/release/controller/IntegracaoExterna/v1.0/agenda/disponibilidade?codEstab=1&dtAgenda={data_busca}&periodo=todos&tpAgd=p&servicos={codigo_servico}'
            
            response = requests.get(url, headers=headers)
            response.raise_for_status()
            
            agendas = response.json()
            
            # Verifica se há QUALQUER terapeuta com horários nesta data E no período escolhido
            tem_horarios = False
            for agenda in agendas:
                data_agenda = agenda.get("data", "")
                if data_agenda != data_busca:
                    continue
                
                horarios = agenda.get("horarios", [])
                for horario in horarios:
                    horarios_prof = horario.get("horarios", [])
                    
                    # Filtra por período
                    for h in horarios_prof:
                        if isinstance(h, dict):
                            hora = h.get("horario", h.get("hora", ""))
                        else:
                            hora = str(h)
                        
                        if hora:
                            try:
                                hora_int = int(hora.split(':')[0])
                                
                                if periodo == "manha" and 6 <= hora_int < 12:
                                    tem_horarios = True
                                    break
                                elif periodo == "tarde" and 12 <= hora_int < 18:
                                    tem_horarios = True
                                    break
                                elif periodo == "noite" and 18 <= hora_int < 24:
                                    tem_horarios = True
                                    break
                            except:
                                pass
                    
                    if tem_horarios:
                        break
                
                if tem_horarios:
                    break
            
            if tem_horarios:
                data_formatada = f"{data_busca} ({dia_semana_pt})"
                datas_com_horarios.append(data_formatada)
                print(f"✅ Data com horários: {data_formatada}")
        
        if not datas_com_horarios:
            print("❌ Nenhuma data com horários encontrada nos próximos 30 dias")
            print("=" * 80)
            return "SEM_DATAS||0"
        
        datas_str = ", ".join(datas_com_horarios)
        quantidade = len(datas_com_horarios)
        
        print(f"✅ {quantidade} datas encontradas")
        print("=" * 80)
        
        return f"TEM_DATAS|{datas_str}|{quantidade}"
    
    except Exception as e:
        print(f"❌ Erro ao buscar próximas datas: {e}")
        print("=" * 80)
        return "SEM_DATAS||0"


@Tool
async def apresentar_confirmacao_agendamento(
    ctx: RunContext[MyDeps]
) -> str:
    """
    Apresenta resumo dos dados do agendamento para confirmação do usuário.
    Deve ser chamada após o usuário escolher o horário.
    
    Returns:
        str: Mensagem formatada com todos os dados para confirmação
    """
    conversation_id = ctx.deps.session_id
    
    # Busca dados do contexto
    session = get_session(conversation_id)
    context = session[2] if session else {}
    
    if isinstance(context, str):
        try:
            context = json.loads(context) if context else {}
        except:
            context = {}
    
    print("=" * 80)
    print("🔍 TOOL: apresentar_confirmacao_agendamento")
    print(f"Conversation ID: {conversation_id}")
    print("=" * 80)
    
    # Extrai dados do contexto
    nome = context.get('nome', 'Não informado')
    unidade = "Buddha Spa - Domiciliar"  # Fixo para domiciliar
    terapia = context.get('terapia', 'Não informada')
    
    # Verifica se é sem preferência de terapeuta
    terapeuta_escolhido = context.get('terapeuta_escolhido', context.get('terapeuta_recorrente', 'Não informado'))
    if terapeuta_escolhido == "sem_preferencia":
        terapeuta = "Sem preferência"
    else:
        terapeuta = terapeuta_escolhido
    
    data = context.get('data_agendamento', 'Não informada')
    horario = context.get('horario_escolhido', 'Não informado')
    telefone = context.get('celular', 'Não informado')
    email = context.get('email', 'Não informado')
    
    # Monta mensagem de confirmação
    mensagem = f"""Obrigado pelas informações! 😊

Antes de confirmar, confira os dados do agendamento:
Pessoa atendida: {nome}
Unidade: {unidade}
Terapia: {terapia}
Terapeuta: {terapeuta}
Data: {data}
Horário: {horario}
Contato: {telefone} | {email}

Está tudo correto?"""
    
    print(f"✅ Mensagem de confirmação montada")
    print("=" * 80)
    
    return mensagem


@Tool
async def buscar_terapeuta_aleatorio_disponivel(
    ctx: RunContext[MyDeps]
) -> str:
    """
    Busca um terapeuta que tenha disponibilidade na data, período e terapia escolhidos.
    Retorna os horários disponíveis do primeiro terapeuta encontrado.
    
    Returns:
        str: "TEM_HORARIOS|nome_terapeuta|horarios|quantidade" ou "SEM_HORARIOS||0"
    """
    conversation_id = ctx.deps.session_id
    
    session = get_session(conversation_id)
    context = session[2] if session else {}
    
    if isinstance(context, str):
        try:
            context = json.loads(context) if context else {}
        except:
            context = {}
    
    codigo_servico = context.get('codigo_servico')
    data_agendamento = context.get('data_agendamento')
    periodo = context.get('periodo')
    
    print("=" * 80)
    print("🔍 TOOL: buscar_terapeuta_aleatorio_disponivel")
    print(f"Conversation ID: {conversation_id}")
    print(f"Código serviço: {codigo_servico}")
    print(f"Data: {data_agendamento}")
    print(f"Período: {periodo}")
    print("=" * 80)
    
    if not codigo_servico or not data_agendamento or not periodo:
        print("❌ Dados insuficientes no contexto")
        print("=" * 80)
        return "ERRO|Dados insuficientes"
    
    headers = {
        'Authorization': os.getenv("LABELLE_TOKEN")
    }
    
    try:
        url = f'https://app.bellesoftware.com.br/api/release/controller/IntegracaoExterna/v1.0/agenda/disponibilidade?codEstab=1&dtAgenda={data_agendamento}&periodo=todos&tpAgd=p&servicos={codigo_servico}'
        
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        
        agendas = response.json()
        print(f"📊 Total de agendas retornadas: {len(agendas)}")
        
        # Busca pela data escolhida
        for agenda in agendas:
            data_agenda = agenda.get("data", "")
            if data_agenda != data_agendamento:
                continue
            
            print(f"✅ Data correta encontrada: {data_agendamento}")
            
            # Percorre terapeutas disponíveis
            horarios = agenda.get("horarios", [])
            for horario in horarios:
                cod_prof = str(horario.get("codProf", "")).strip()
                nome_prof = horario.get("nome", "")
                
                # Extrai horários do terapeuta
                horarios_prof = horario.get("horarios", [])
                horarios_encontrados = []
                
                if isinstance(horarios_prof, list):
                    for h in horarios_prof:
                        if isinstance(h, dict):
                            hora = h.get("horario", h.get("hora", ""))
                        else:
                            hora = str(h)
                        if hora:
                            horarios_encontrados.append(hora)
                
                # Também verifica campo "hora" direto
                hora_direta = horario.get("hora", "")
                if hora_direta and hora_direta not in horarios_encontrados:
                    horarios_encontrados.append(hora_direta)
                
                # Filtra horários por período escolhido
                horarios_filtrados = []
                for h in horarios_encontrados:
                    try:
                        hora_int = int(h.split(':')[0])
                        
                        if periodo == "manha" and 6 <= hora_int < 12:
                            horarios_filtrados.append(h)
                        elif periodo == "tarde" and 12 <= hora_int < 18:
                            horarios_filtrados.append(h)
                        elif periodo == "noite" and 18 <= hora_int < 24:
                            horarios_filtrados.append(h)
                    except:
                        horarios_filtrados.append(h)
                
                # 🔥 VALIDAÇÃO CRÍTICA: Considera duração da terapia + 10 min de intervalo
                if horarios_filtrados:
                    # Busca duração da terapia no contexto
                    duracao_terapia = None
                    
                    # Tenta extrair duração de variacoes_terapia
                    variacoes = context.get('variacoes_terapia', [])
                    terapia_escolhida = context.get('terapia', '')
                    
                    if variacoes:
                        for v in variacoes:
                            if v.get('nome') == terapia_escolhida:
                                duracao_terapia = v.get('tempo')
                                print(f"  ⏱️ Duração da terapia encontrada em variações: {duracao_terapia} min")
                                break
                    
                    # Se não encontrou em variações, tenta extrair do nome da terapia
                    if not duracao_terapia and terapia_escolhida:
                        import re
                        match = re.search(r'\b(\d+)\b', terapia_escolhida)
                        if match:
                            duracao_terapia = int(match.group(1))
                            print(f"  ⏱️ Duração da terapia extraída do nome: {duracao_terapia} min")
                    
                    # Se ainda não encontrou, usa duração padrão de 60 min
                    if not duracao_terapia:
                        duracao_terapia = 60
                        print(f"  ⚠️ Duração não encontrada, usando padrão: {duracao_terapia} min")
                    
                    # Aplica validação de duração + intervalo
                    horarios_validos = validar_horarios_com_duracao(
                        horarios_disponiveis=horarios_filtrados,
                        duracao_terapia=duracao_terapia,
                        intervalo_minutos=10
                    )
                    
                    # Se encontrou horários VÁLIDOS, retorna este terapeuta
                    if horarios_validos:
                        # Armazena terapeuta no contexto
                        update_context(conversation_id, {
                            "terapeuta_codProf": cod_prof,
                            "terapeuta_escolhido": nome_prof,
                            "horarios_disponiveis": horarios_validos
                        })
                        
                        horarios_str = ", ".join(horarios_validos)
                        print(f"✅ Terapeuta encontrado: {nome_prof} (cod: {cod_prof})")
                        print(f"✅ {len(horarios_validos)} horários VÁLIDOS (com duração + intervalo)")
                        print("=" * 80)
                        
                        return f"TEM_HORARIOS|{nome_prof}|{horarios_str}|{len(horarios_validos)}"
        
        print("❌ Nenhum terapeuta com horários disponíveis no período escolhido")
        print("=" * 80)
        return "SEM_HORARIOS||0"
    
    except Exception as e:
        print(f"❌ Erro ao buscar terapeuta: {e}")
        print("=" * 80)
        return "ERRO|Erro ao consultar API"

@Tool
async def finalizar_agendamento_pacote(
    ctx: RunContext[MyDeps]
) -> str:
    """
    Finaliza o agendamento chamando a API da Belle Software.
    Deve ser chamada apenas após confirmação do usuário.
    
    Returns:
        str: Mensagem de sucesso ou erro do agendamento
    """
    conversation_id = ctx.deps.session_id
    
    # Busca dados do contexto
    session = get_session(conversation_id)
    context = session[2] if session else {}
    
    if isinstance(context, str):
        try:
            context = json.loads(context) if context else {}
        except:
            context = {}
    
    print("=" * 80)
    print("🔍 TOOL: finalizar_agendamento_pacote")
    print(f"Conversation ID: {conversation_id}")
    print("=" * 80)
    
    # Valida dados obrigatórios
    codigo_usuario = context.get("codigo_usuario")
    if not codigo_usuario or str(codigo_usuario).strip().lower() in ("none", "null", ""):
        print("❌ Código do cliente inválido")
        print("=" * 80)
        return "❌ Não foi possível finalizar: código do cliente inválido."
    
    # Extrai dados do contexto
    terapeuta_escolhido_ctx = context.get("terapeuta_escolhido", context.get("terapeuta_recorrente"))
    
    # Verifica se é sem preferência de terapeuta
    sem_preferencia = (terapeuta_escolhido_ctx == "sem_preferencia")
    
    if sem_preferencia:
        # Sem preferência: campos de terapeuta vazios
        terapeuta_cod = ""
        terapeuta_nome = ""
        print("ℹ️ Agendamento SEM TERAPEUTA (sem preferência)")
    else:
        # Com terapeuta específico
        terapeuta_cod = context.get("terapeuta_codProf", "")
        terapeuta_nome = terapeuta_escolhido_ctx or ""
    
    data_agendamento = context.get("data_agendamento")
    horario_escolhido = context.get("horario_escolhido")
    codigo_servico = context.get("codigo_servico")
    terapia = context.get("terapia")
    tipo_beneficio = context.get("tipo_beneficio", "")
    cod_plano = context.get("cod_plano")  # 🔥 Código do plano para desconto de saldo
    
    # Valida campos obrigatórios (terapeuta é opcional quando sem_preferencia = True)
    if not all([data_agendamento, horario_escolhido, codigo_servico]):
        print("❌ Dados insuficientes para agendamento")
        print(f"data_agendamento: {data_agendamento}")
        print(f"horario_escolhido: {horario_escolhido}")
        print(f"codigo_servico: {codigo_servico}")
        print("=" * 80)
        return "❌ Não foi possível finalizar: dados incompletos."
    
    # 🔥 Monta observação dinâmica: "Agendamento via chatbot - [Tipo] - Código: [codigo]"
    observacao_partes = ["Agendamento via chatbot"]
    
    if tipo_beneficio == "pacote":
        observacao_partes.append("Pacote")
        codigo_cliente_pacote = context.get("codigo_cliente_pacote")
        if codigo_cliente_pacote:
            observacao_partes.append(f"Código: {codigo_cliente_pacote}")
    elif tipo_beneficio == "voucher":
        observacao_partes.append("Voucher")
        voucher = context.get("voucher")
        if voucher:
            observacao_partes.append(f"Código: {voucher}")
    elif tipo_beneficio == "vale":
        observacao_partes.append("Vale Bem-Estar")
        voucher = context.get("voucher")
        if voucher:
            observacao_partes.append(f"Código: {voucher}")
    
    observacao = " - ".join(observacao_partes)
    
    # 🔥 EXTRAI DURAÇÃO REAL DA TERAPIA (não usar hardcoded 60)
    duracao_terapia = None
    
    # Tenta extrair duração de variacoes_terapia
    variacoes = context.get('variacoes_terapia', [])
    if variacoes:
        for v in variacoes:
            if v.get('nome') == terapia:
                duracao_terapia = v.get('tempo')
                print(f"⏱️ Duração da terapia encontrada em variações: {duracao_terapia} min")
                break
    
    # Se não encontrou em variações, tenta extrair do nome da terapia (ex: "Reflexologia 30" → 30)
    if not duracao_terapia and terapia:
        import re
        match = re.search(r'\b(\d+)\b', terapia)
        if match:
            duracao_terapia = int(match.group(1))
            print(f"⏱️ Duração da terapia extraída do nome: {duracao_terapia} min")
    
    # Se ainda não encontrou, usa duração padrão de 60 min
    if not duracao_terapia:
        duracao_terapia = 60
        print(f"⚠️ Duração não encontrada, usando padrão: {duracao_terapia} min")
    
    # Monta payload para API
    payload = {
        "codCli": codigo_usuario,
        "codEstab": 1,
        "prof": {
            "cod_usuario": terapeuta_cod,
            "nom_usuario": terapeuta_nome
        },
        "dtAgd": data_agendamento,
        "hri": horario_escolhido,
        "serv": [
            {
                "codServico": codigo_servico,
                "nome": terapia,
                "label": terapia,
                "valor": "0",  # Pacote não tem valor
                "tempo": duracao_terapia  # 🔥 Duração REAL da terapia
            }
        ],
        "codPlano": cod_plano if cod_plano else "",  # 🔥 Envia codPlano para desconto de saldo
        "agSala": True,
        "codSala": context.get("codSala", ""),  # 🆕 Código da sala do contexto
        "codVendedor": "",
        "codEquipamento": 1,
        "observacao": observacao
    }
    
    print(f"📦 Payload do agendamento:")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    
    url = 'https://app.bellesoftware.com.br/api/release/controller/IntegracaoExterna/v1.0/agenda/gravar'
    
    headers = {
        'Authorization': os.getenv("LABELLE_TOKEN"),
        'Content-Type': 'application/json'
    }
    
    try:
        response = requests.post(url, headers=headers, json=payload)
        response.raise_for_status()
        
        data = response.json()
        print(f"📥 Resposta da API:")
        print(json.dumps(data, ensure_ascii=False, indent=2))
        
        # Verifica se horário está disponível
        if not data.get("dis", False):
            print(f"❌ Horário indisponível: {data.get('msg', 'erro desconhecido')}")
            print("=" * 80)
            return f"❌ HORÁRIO INDISPONÍVEL: {data.get('msg', 'erro desconhecido')}. Escolha outro horário."
        
        print("✅ Agendamento realizado com sucesso!")
        print("=" * 80)
        
        # Limpa flag de reagendamento se existir
        if context.get("em_reagendamento"):
            update_context(conversation_id, {
                "em_reagendamento": False
            })
            print("🔄 Flag em_reagendamento limpa após sucesso do reagendamento")
        
        # Mensagem personalizada de sucesso
        nome = context.get("nome", "Cliente")
        return f"✅ {nome}, agendamento confirmado!\nA experiência já está reservada e a unidade aguarda sua visita com carinho. 🥰"
    
    except Exception as e:
        print(f"❌ Erro ao finalizar agendamento: {e}")
        try:
            print(f"Response text: {response.text}")
        except:
            pass
        print("=" * 80)
        return f"❌ Erro ao finalizar agendamento: {str(e)}"


# ============================================================================     
# TOOLS PARA CANCELAMENTO
# ============================================================================

@Tool
def consultas_cliente(ctx: RunContext[MyDeps], cpf: str = "") -> str:
    """
    Consulta os agendamentos do cliente.
    
    Args:
        cpf: CPF do cliente para consulta (opcional). Se não informado, usa o CPF do contexto.
    
    Returns:
        str: Lista de agendamentos ou mensagem de erro
    """
    print("🔍 DEBUG - INICIANDO CONSULTA DE AGENDAMENTOS")
    print("=" * 80)
    
    # Busca dados do contexto
    conversation_id = ctx.deps.session_id
    session = get_session(conversation_id)
    context = session[2] if session else {}
    
    if isinstance(context, str):
        try:
            context = json.loads(context) if context else {}
        except:
            context = {}
    
    # Se foi informado um CPF, usa ele (como em consultar_pacotes)
    if cpf:
        print(f"🔍 CPF informado pelo usuário: {cpf}")
        
        # Normaliza CPF (remove pontos, traços, etc) - igual a consultar_pacotes
        cpf_numeros = ''.join(filter(str.isdigit, cpf))
        
        headers = {'Authorization': os.getenv("LABELLE_TOKEN")}
        
        try:
            # ETAPA 1: Buscar cliente por CPF - igual a consultar_pacotes
            url_cliente = f'https://app.bellesoftware.com.br/api/release/controller/IntegracaoExterna/v1.0/cliente/listar?cpf={cpf_numeros}&id=&codEstab=1&email=&celular='
            print(f"URL cliente: {url_cliente}")
            
            response = requests.get(url_cliente, headers=headers)
            print(f"Status cliente: {response.status_code}")
            response.raise_for_status()
            data_cliente = response.json()
            print(f"Resposta cliente (tipo): {type(data_cliente)}")
            print(f"Resposta cliente: {data_cliente}")
            
            # Verifica se encontrou cliente - igual a consultar_pacotes
            if not data_cliente:
                print("❌ Cliente não encontrado pelo CPF informado")
                return "❌ Não encontrei seu cadastro com o CPF informado. Por favor, verifique o CPF ou entre em contato com a unidade."
            
            # Se for lista, pega primeiro item - igual a consultar_pacotes
            if isinstance(data_cliente, list):
                if len(data_cliente) == 0:
                    print("❌ Cliente não encontrado pelo CPF informado")
                    return "❌ Não encontrei seu cadastro com o CPF informado. Por favor, verifique o CPF ou entre em contato com a unidade."
                cliente = data_cliente[0]
            else:
                cliente = data_cliente
            
            print(f"Cliente encontrado: {cliente}")
            
            # Pega o código (ID) do cliente - igual a consultar_pacotes
            codigo_cliente = cliente.get("codigo")
            nome = cliente.get("nome", "Cliente")
            print(f"Código do cliente: {codigo_cliente}")
            print(f"Nome do cliente: {nome}")
            
            if not codigo_cliente:
                print("❌ Não foi possível identificar seu cadastro")
                return "❌ Não foi possível identificar seu cadastro. Por favor, entre em contato com a unidade."
            
            # Atualiza contexto com os dados encontrados
            update_context(conversation_id, {
                "codigo_usuario": codigo_cliente,
                "nome": nome,
                "cpf": cpf_numeros
            })
            
            print(f"✅ Cliente encontrado pelo CPF informado: {nome} (código: {codigo_cliente})")
            
        except Exception as e:
            print(f"❌ Erro ao buscar cliente pelo CPF informado: {e}")
            return "❌ Erro ao consultar seu cadastro com o CPF informado. Tente novamente mais tarde."
    
    else:
        # Se não foi informado CPF, usa o fluxo original (contexto)
        nome = context.get("nome", "Cliente")
        codigo_cliente = context.get("codigo_usuario")
        
        print(f"👤 Dados do cliente do contexto:")
        print(f"   Nome: {nome}")
        print(f"   Código: {codigo_cliente}")
        
        # Se não tem código_cliente, tenta buscar pelo CPF do contexto
        if not codigo_cliente:
            cpf_contexto = context.get("cpf", "")
            if cpf_contexto:
                print(f"🔍 Código não encontrado, tentando buscar pelo CPF do contexto: {cpf_contexto}")
                
                # Usa a mesma lógica de consultar_pacotes
                cpf_numeros = ''.join(filter(str.isdigit, cpf_contexto))
                headers = {'Authorization': os.getenv("LABELLE_TOKEN")}
                
                try:
                    url_cliente = f'https://app.bellesoftware.com.br/api/release/controller/IntegracaoExterna/v1.0/cliente/listar?cpf={cpf_numeros}&id=&codEstab=1&email=&celular='
                    response = requests.get(url_cliente, headers=headers)
                    response.raise_for_status()
                    data_cliente = response.json()
                    
                    if data_cliente:
                        cliente = data_cliente[0] if isinstance(data_cliente, list) else data_cliente
                        codigo_cliente = cliente.get("codigo")
                        nome = cliente.get("nome", "Cliente")
                        
                        # Atualiza contexto
                        update_context(conversation_id, {
                            "codigo_usuario": codigo_cliente,
                            "nome": nome
                        })
                        
                        print(f"✅ Cliente encontrado pelo CPF do contexto: {nome} (código: {codigo_cliente})")
                    else:
                        print("❌ Cliente não encontrado pelo CPF do contexto")
                        return "❌ Não encontrei seu cadastro. Por favor, informe seu CPF ou entre em contato com a unidade."
                        
                except Exception as e:
                    print(f"❌ Erro ao buscar cliente pelo CPF do contexto: {e}")
                    return "❌ Erro ao consultar seu cadastro. Tente novamente mais tarde."
        
        if not codigo_cliente:
            print("❌ Código do cliente não encontrado")
            return "❌ Não encontrei seu código no contexto. Por favor, informe seu CPF ou faça o login para consultar os agendamentos."
    
    if not codigo_cliente:
        print("❌ Código do cliente não encontrado após todas as tentativas")
        return "❌ Não foi possível identificar seu cadastro. Por favor, informe seu CPF ou faça o login para consultar os agendamentos."
    
    print(f"👤 Dados finais do cliente:")
    print(f"   Nome: {nome}")
    print(f"   Código: {codigo_cliente}")
    print("=" * 80)
    
    # Define período de consulta (próximos 3 meses)
    from datetime import datetime, timedelta
    dt_inicio = datetime.now().strftime("%d/%m/%Y")
    dt_fim = (datetime.now() + timedelta(days=90)).strftime("%d/%m/%Y")
    
    # Chama API para consultar agendamentos
    url = f'https://app.bellesoftware.com.br/api/release/controller/IntegracaoExterna/v1.0/cliente/agenda?codCliente={codigo_cliente}&codEstab=1&dtInicio={dt_inicio}&dtFim={dt_fim}'
    
    headers = {
        'Authorization': os.getenv("LABELLE_TOKEN")
    }
    
    print(f"📞 Chamando API para consultar agendamentos...")
    print(f"📞 URL: {url}")
    
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        
        data = response.json()
        print(f"📥 Resposta da API:")
        print(json.dumps(data, ensure_ascii=False, indent=2))
        
        # Verifica se há agendamentos
        agendamentos = data if isinstance(data, list) else data.get("agenda", [])
        
        if not agendamentos or len(agendamentos) == 0:
            print("❌ Nenhum agendamento encontrado")
            print("=" * 80)
            return f"❌ {nome}, não encontrei nenhum agendamento cadastrado para o período."
        
        # Formata lista de agendamentos
        mensagem = f"✅ {nome}, aqui estão seus agendamentos:\n\n"
        
        for i, agendamento in enumerate(agendamentos, 1):
            # Adaptado para a estrutura real da API
            data_agenda = agendamento.get("dtAgenda", "")
            hora = agendamento.get("hrConsulta", "")
            profissional = agendamento.get("prof", {}).get("nome", "")
            servico = ""
            if agendamento.get("servicos") and len(agendamento.get("servicos", [])) > 0:
                servico = agendamento.get("servicos", [])[0].get("nome", "")
            codConsulta = agendamento.get("codConsulta", "")
            
            mensagem += f"{i}. {data_agenda} às {hora}\n"
            mensagem += f"   Profissional: {profissional}\n"
            mensagem += f"   Serviço: {servico}\n"
            mensagem += f"   Código: {codConsulta}\n\n"
        
        print("✅ Consulta de agendamentos concluída")
        print("=" * 80)
        return mensagem
        
    except Exception as e:
        print(f"❌ Erro ao consultar agendamentos: {e}")
        try:
            print(f"Response text: {response.text}")
        except:
            pass
        print("=" * 80)
        return f" Erro ao consultar agendamentos: {str(e)}"

@Tool
def cancelar_agendamento(ctx: RunContext[MyDeps], numero_agendamento: int) -> str:
    """
    Cancela um agendamento do cliente com base no número escolhido.
    
    Args:
        ctx: RunContext com dependências e session_id
        numero_agendamento: Número do agendamento a ser cancelado (baseado na lista retornada por consultas_cliente)
        
    Returns:
        str: Mensagem de confirmação ou erro
    """
    print(" DEBUG - INICIANDO CANCELAMENTO DE AGENDAMENTO")
    print("=" * 80)
    
    # Busca dados do contexto
    conversation_id = ctx.deps.session_id
    session = get_session(conversation_id)
    context = session[2] if session else {}
    
    if isinstance(context, str):
        try:
            context = json.loads(context) if context else {}
        except:
            context = {}
    
    nome = context.get("nome", "Cliente")
    codigo_cliente = context.get("codigo_usuario")
    
    print(f" Dados do cliente:")
    print(f"   Nome: {nome}")
    print(f"   Código: {codigo_cliente}")
    print(f"   Número do agendamento escolhido: {numero_agendamento}")
    print("=" * 80)
    
    if not codigo_cliente:
        print(" Código do cliente não encontrado no contexto")
        print("=" * 80)
        return " Não encontrei seu código no contexto. Por favor, faça o login para cancelar agendamentos."
    
    # Primeiro, consulta os agendamentos para obter o codConsulta
    from datetime import datetime, timedelta
    dt_inicio = datetime.now().strftime("%d/%m/%Y")
    dt_fim = (datetime.now() + timedelta(days=90)).strftime("%d/%m/%Y")
    
    url = f'https://app.bellesoftware.com.br/api/release/controller/IntegracaoExterna/v1.0/cliente/agenda?codCliente={codigo_cliente}&codEstab=1&dtInicio={dt_inicio}&dtFim={dt_fim}'
    
    headers = {
        'Authorization': os.getenv("LABELLE_TOKEN")
    }
    
    print(f" Consultando agendamentos para encontrar o codConsulta...")
    
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        
        data = response.json()
        print(f" Resposta da API:")
        print(json.dumps(data, ensure_ascii=False, indent=2))
        
        # Verifica se há agendamentos
        # A API retorna uma lista diretamente, não um objeto com "agenda"
        agendamentos = data if isinstance(data, list) else data.get("agenda", [])
        
        if not agendamentos or len(agendamentos) == 0:
            print(" Nenhum agendamento encontrado")
            print("=" * 80)
            return f" {nome}, não encontrei nenhum agendamento cadastrado para o período."
        
        if numero_agendamento < 1 or numero_agendamento > len(agendamentos):
            print(f" Número de agendamento inválido: {numero_agendamento}")
            print("=" * 80)
            return f" Número de agendamento inválido. Por favor, escolha um número de 1 a {len(agendamentos)}."
        
        # Pega o agendamento escolhido (índice -1 porque começa em 0)
        agendamento_escolhido = agendamentos[numero_agendamento - 1]
        codConsulta = agendamento_escolhido.get("codConsulta")
        
        if not codConsulta:
            print(" codConsulta não encontrado no agendamento")
            print("=" * 80)
            return " Não foi possível encontrar o código da consulta para cancelamento."
        
        print(f" Agendamento encontrado para cancelamento:")
        print(f"   codConsulta: {codConsulta}")
        print(f"   Data: {agendamento_escolhido.get('dtAgenda', '')}")
        print(f"   Hora: {agendamento_escolhido.get('hrConsulta', '')}")
        
        # Agora cancela o agendamento
        url_cancelar = 'https://app.bellesoftware.com.br/api/release/controller/IntegracaoExterna/v1.0/agenda/status'
        
        payload = {
            "codConsulta": codConsulta,
            "novoStatus": "Cancelado"
        }
        
        print(f" Payload do cancelamento:")
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        
        response_cancelar = requests.put(url_cancelar, headers=headers, json=payload)
        response_cancelar.raise_for_status()
        
        data_cancelar = response_cancelar.json()
        print(f" Resposta da API de cancelamento:")
        print(json.dumps(data_cancelar, ensure_ascii=False, indent=2))
        
        # Verifica se cancelamento foi bem-sucedido
        if data_cancelar.get("sucesso", False):
            print(" Agendamento cancelado com sucesso!")
            print("=" * 80)
            return f" {nome}, seu agendamento para {agendamento_escolhido.get('dtAgenda', '')} às {agendamento_escolhido.get('hrConsulta', '')} foi cancelado com sucesso. Se precisar remarcar, estaremos aqui para ajudar! "
        else:
            print(f" Erro ao cancelar agendamento: {data_cancelar.get('mensagem', 'erro desconhecido')}")
            print("=" * 80)
            return f" Erro ao cancelar agendamento: {data_cancelar.get('mensagem', 'erro desconhecido')}"
        
    except Exception as e:
        print(f" Erro ao cancelar agendamento: {e}")
        try:
            print(f"Response text: {response.text}")
        except:
            pass
        print("=" * 80)
        return f" Erro ao cancelar agendamento: {str(e)}"

@Tool
def cancelar_e_preparar_reagendamento(ctx: RunContext[MyDeps], numero_agendamento: int) -> str:
    """
    Cancela um agendamento e prepara o contexto para reagendamento.
    Captura os dados do agendamento (terapia, código do serviço) antes de cancelar
    e seta a flag em_reagendamento no contexto.
    
    Args:
        ctx: RunContext com dependências e session_id
        numero_agendamento: Número do agendamento a ser cancelado
        
    Returns:
        str: Mensagem de confirmação ou erro
    """
    print("🔄 DEBUG - CANCELAR E PREPARAR REAGENDAMENTO")
    print("=" * 80)
    
    # Busca dados do contexto
    conversation_id = ctx.deps.session_id
    session = get_session(conversation_id)
    context = session[2] if session else {}
    
    if isinstance(context, str):
        try:
            context = json.loads(context) if context else {}
        except:
            context = {}
    
    nome = context.get("nome", "Cliente")
    codigo_cliente = context.get("codigo_usuario")
    
    print(f"📋 Dados do cliente:")
    print(f"   Nome: {nome}")
    print(f"   Código: {codigo_cliente}")
    print(f"   Número do agendamento escolhido: {numero_agendamento}")
    print("=" * 80)
    
    if not codigo_cliente:
        print("❌ Código do cliente não encontrado no contexto")
        print("=" * 80)
        return "❌ Não encontrei seu código no contexto."
    
    # Consulta os agendamentos para obter os dados
    from datetime import datetime, timedelta
    dt_inicio = datetime.now().strftime("%d/%m/%Y")
    dt_fim = (datetime.now() + timedelta(days=90)).strftime("%d/%m/%Y")
    
    url = f'https://app.bellesoftware.com.br/api/release/controller/IntegracaoExterna/v1.0/cliente/agenda?codCliente={codigo_cliente}&codEstab=1&dtInicio={dt_inicio}&dtFim={dt_fim}'
    
    headers = {
        'Authorization': os.getenv("LABELLE_TOKEN")
    }
    
    print(f"🔍 Consultando agendamentos...")
    
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        
        data = response.json()
        agendamentos = data if isinstance(data, list) else data.get("agenda", [])
        
        if not agendamentos or len(agendamentos) == 0:
            print("❌ Nenhum agendamento encontrado")
            print("=" * 80)
            return f"❌ {nome}, não encontrei nenhum agendamento cadastrado."
        
        if numero_agendamento < 1 or numero_agendamento > len(agendamentos):
            print(f"❌ Número de agendamento inválido: {numero_agendamento}")
            print("=" * 80)
            return f"❌ Número de agendamento inválido. Escolha um número de 1 a {len(agendamentos)}."
        
        # Pega o agendamento escolhido
        agendamento_escolhido = agendamentos[numero_agendamento - 1]
        codConsulta = agendamento_escolhido.get("codConsulta")
        
        # CAPTURA OS DADOS DO AGENDAMENTO ANTES DE CANCELAR
        servicos = agendamento_escolhido.get("servicos", [])
        if servicos and len(servicos) > 0:
            cod_servico = servicos[0].get("cod")
            nome_terapia = servicos[0].get("nome")
            
            print(f"📦 Dados capturados do agendamento:")
            print(f"   Terapia: {nome_terapia}")
            print(f"   Código do serviço: {cod_servico}")
            print(f"   Tipo benefício atual: {context.get('tipo_beneficio', 'NÃO DEFINIDO')}")
            print("=" * 80)
            
            # SETA FLAG DE REAGENDAMENTO COM OS DADOS
            # IMPORTANTE: Usar 'codigo_servico' (padrão das outras tools) ao invés de 'cod_servico'
            update_context(conversation_id, {
                "em_reagendamento": True,
                "terapia": nome_terapia,
                "codigo_servico": cod_servico,  # MUDADO: codigo_servico ao invés de cod_servico
                "cod_servico": cod_servico  # Mantém ambos por compatibilidade
            })
            # NÃO sobrescrever tipo_beneficio - ele já existe no contexto
            
            # ATUALIZA ctx.deps DIRETAMENTE para garantir que ir_para_agendamento detecte
            ctx.deps.em_reagendamento = True
            ctx.deps.terapia = nome_terapia
            ctx.deps.cod_servico = cod_servico
            # NÃO sobrescrever tipo_beneficio se já existir
            
            print("✅ Flag em_reagendamento setada com dados da terapia!")
            print(f"✅ ctx.deps.em_reagendamento = {ctx.deps.em_reagendamento}")
            print(f"✅ ctx.deps.terapia = {ctx.deps.terapia}")
            print(f"✅ ctx.deps.cod_servico = {ctx.deps.cod_servico}")
            print(f"✅ ctx.deps.tipo_beneficio = {ctx.deps.tipo_beneficio}")
        
        if not codConsulta:
            print("❌ codConsulta não encontrado")
            print("=" * 80)
            return "❌ Não foi possível encontrar o código da consulta."
        
        print(f"🔍 Agendamento encontrado:")
        print(f"   codConsulta: {codConsulta}")
        print(f"   Data: {agendamento_escolhido.get('dtAgenda', '')}")
        print(f"   Hora: {agendamento_escolhido.get('hrConsulta', '')}")
        
        # Cancela o agendamento
        url_cancelar = 'https://app.bellesoftware.com.br/api/release/controller/IntegracaoExterna/v1.0/agenda/status'
        
        payload = {
            "codConsulta": codConsulta,
            "novoStatus": "Cancelado"
        }
        
        response_cancelar = requests.put(url_cancelar, headers=headers, json=payload)
        response_cancelar.raise_for_status()
        
        data_cancelar = response_cancelar.json()
        
        if data_cancelar.get("sucesso", False):
            print("✅ Agendamento cancelado com sucesso!")
            print("=" * 80)
            return "SUCESSO_REAGENDAMENTO"  # Retorno especial para o agente detectar
        else:
            print(f"❌ Erro ao cancelar: {data_cancelar.get('mensagem', 'erro desconhecido')}")
            print("=" * 80)
            return f"❌ Erro ao cancelar agendamento: {data_cancelar.get('mensagem', 'erro desconhecido')}"
        
    except Exception as e:
        print(f"❌ Erro ao cancelar agendamento: {e}")
        print("=" * 80)
        return f"❌ Erro ao cancelar agendamento: {str(e)}"

@Tool
def ir_para_cancelamento(ctx: RunContext[MyDeps]) -> str:
    """
    Realiza a transição do fluxo atual para o agente de cancelamento de agendamentos.
    
    Deve ser chamada quando o usuário expressar intenção de cancelar um atendimento.
    """
    from store.database import update_current_agent

    conversation_id = ctx.deps.session_id

    print("=" * 80)
    print("DEBUG IR_PARA_CANCELAMENTO - INICIANDO TRANSIÇÃO")
    print(f"Conversation ID: {conversation_id}")
    print("=" * 80)

    try:
        update_current_agent(conversation_id, "cancelamento_agent")

        print("✅ Transição para cancelamento_agent realizada com sucesso!")
        print("=" * 80)

        return ""

    except Exception as e:
        print(f"❌ Erro ao atualizar agente: {e}")
        print("=" * 80)

@Tool
def ir_para_reagendamento(ctx: RunContext[MyDeps]) -> str:
    """
    Realiza a transição do fluxo atual para o agente de reagendamento de agendamentos.
    
    Deve ser chamada quando o usuário expressar intenção de reagendar um atendamento.
    """
    from store.database import update_current_agent

    conversation_id = ctx.deps.session_id

    print("=" * 80)
    print("DEBUG IR_PARA_REAGENDAMENTO - INICIANDO TRANSIÇÃO")
    print(f"Conversation ID: {conversation_id}")
    print("=" * 80)

    try:
        update_current_agent(conversation_id, "reagendamento_agent")

        print("✅ Transição para reagendamento_agent realizada com sucesso!")
        print("=" * 80)

        return ""

    except Exception as e:
        print(f"❌ Erro ao atualizar agente: {e}")
        print("=" * 80)
        
        return f"❌ Erro ao iniciar reagendamento: {str(e)}"

@Tool
def registrar_step(ctx: RunContext[MyDeps], step: str) -> str:
    """
    Registra um step de navegação no histórico (uso interno, não mostrar ao usuário).
    
    Args:
        step: Nome do step (ex: "validou_voucher", "escolheu_terapia")
    
    Returns:
        Confirmação silenciosa
    """
    if ctx.deps.steps is None:
        ctx.deps.steps = []
    
    ctx.deps.steps.append(step)
    
    return "ok"