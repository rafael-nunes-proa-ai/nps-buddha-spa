"""
Módulo de processamento automático de cadastro.
Extrai dados do histórico de mensagens e cria cadastro via API.
"""
import re
import requests
import os
from datetime import datetime
from store.database import get_session, update_context

def _somente_numeros(texto: str | None) -> str:
    """Remove todos os caracteres não numéricos de um texto."""
    if not texto:
        return ""
    return ''.join(filter(str.isdigit, texto))

def _extrair_dados_do_historico(messages):
    """
    Extrai os dados de cadastro do histórico de mensagens.
    
    Ordem esperada das respostas do usuário:
    1. Nome completo
    2. Celular
    3. Data de nascimento
    4. Email
    5. CPF
    6. Gênero
    """
    print("=" * 80)
    print("🔍 DEBUG _extrair_dados_do_historico - INÍCIO")
    print(f"Total de mensagens no histórico: {len(messages)}")
    
    # Filtra apenas mensagens do usuário (kind='request')
    user_messages = []
    for msg in messages:
        if hasattr(msg, 'kind') and msg.kind == 'request':
            # Extrai o conteúdo da mensagem
            if hasattr(msg, 'parts') and msg.parts:
                content = msg.parts[0].content if hasattr(msg.parts[0], 'content') else str(msg.parts[0])
                # Ignora dicts (tool responses), mensagens vazias e mensagens de erro
                if isinstance(content, str) and content.strip():
                    # Ignora mensagens de erro de tools
                    if 'Unknown tool name' not in content and 'Available tools' not in content:
                        user_messages.append(content)
    
    print(f"Mensagens do usuário encontradas: {len(user_messages)}")
    for i, msg in enumerate(user_messages):
        print(f"  [{i}]: {msg}")
    
    # Precisamos identificar as 6 respostas após a pergunta "nome completo"
    # Procura pelo índice onde começa a coleta
    # A coleta começa após o último "SIM" (resposta para "O atendimento é para você mesmo?")
    inicio_coleta = -1
    for i in range(len(user_messages) - 1, -1, -1):  # Busca de trás pra frente
        msg = user_messages[i].lower().strip()
        if msg in ['sim', 's', 'yes', 'isso']:
            # Verifica se a próxima mensagem parece ser um nome (2+ palavras)
            if i + 1 < len(user_messages):
                proxima = user_messages[i + 1].strip()
                # Nome deve ter pelo menos 2 palavras e não ser um número
                if len(proxima.split()) >= 2 and not proxima.replace(' ', '').isdigit():
                    inicio_coleta = i + 1
                    break
    
    if inicio_coleta == -1:
        print("❌ Não foi possível identificar o início da coleta de dados")
        print("=" * 80)
        return None
    
    print(f"✅ Início da coleta identificado no índice: {inicio_coleta}")
    print(f"   Mensagem de início: {user_messages[inicio_coleta][:50]}...")
    
    # Extrai os 6 campos a partir do início da coleta
    # IMPORTANTE: Precisa ter EXATAMENTE 6 mensagens do usuário após o início
    if inicio_coleta + 6 > len(user_messages):
        print(f"❌ Não há mensagens suficientes após o início (precisa de 6, tem {len(user_messages) - inicio_coleta})")
        print("=" * 80)
        return None
    
    nome = user_messages[inicio_coleta].strip()
    celular = _somente_numeros(user_messages[inicio_coleta + 1])
    dtNascimento = user_messages[inicio_coleta + 2].strip()
    email = user_messages[inicio_coleta + 3].strip()
    cpf_raw = user_messages[inicio_coleta + 4].strip()
    genero_raw = user_messages[inicio_coleta + 5].strip()
    
    # 🔥 VALIDAÇÃO CRÍTICA: Verifica se CPF e GÊNERO não são respostas de tools
    # (ex: "VALIDO", "INVALIDO|...", etc)
    if cpf_raw.upper().startswith("VALIDO") or cpf_raw.upper().startswith("INVALIDO"):
        print(f"❌ CPF detectado como resposta de tool: {cpf_raw}")
        print("=" * 80)
        return None
    
    if genero_raw.upper().startswith("VALIDO") or genero_raw.upper().startswith("INVALIDO"):
        print(f"❌ Gênero detectado como resposta de tool: {genero_raw}")
        print("=" * 80)
        return None
    
    cpf = _somente_numeros(cpf_raw)
    genero = genero_raw.lower()
    
    # Normaliza gênero (API Belle aceita: Masculino, Feminino ou Outros)
    if 'masc' in genero:
        genero = 'Masculino'
    elif 'fem' in genero:
        genero = 'Feminino'
    else:
        genero = 'Outros'
    
    dados = {
        'nome': nome,
        'celular': celular,
        'dtNascimento': dtNascimento,
        'email': email,
        'cpf': cpf,
        'genero': genero
    }
    
    print("✅ Dados extraídos:")
    for k, v in dados.items():
        print(f"  {k}: {v}")
    print("=" * 80)
    
    return dados

def _validar_dados_basicos(dados):
    """Valida se os dados básicos estão presentes e no formato correto."""
    print("=" * 80)
    print("🔍 DEBUG _validar_dados_basicos - INÍCIO")
    
    # Validações básicas
    if not dados.get('nome') or len(dados['nome'].split()) < 2:
        print("❌ Nome inválido (precisa ter pelo menos 2 palavras)")
        print("=" * 80)
        return False
    
    if not dados.get('celular') or len(dados['celular']) < 10:
        print(f"❌ Celular inválido (tem {len(dados.get('celular', ''))} dígitos, precisa de pelo menos 10)")
        print("=" * 80)
        return False
    
    if not dados.get('cpf') or len(dados['cpf']) != 11:
        print(f"❌ CPF inválido (tem {len(dados.get('cpf', ''))} dígitos, precisa de 11)")
        print("=" * 80)
        return False
    
    if not dados.get('email') or '@' not in dados['email']:
        print("❌ Email inválido (não contém @)")
        print("=" * 80)
        return False
    
    # Valida formato de data DD/MM/AAAA
    if dados.get('dtNascimento'):
        if not re.match(r'^\d{2}/\d{2}/\d{4}$', dados['dtNascimento']):
            print(f"❌ Data de nascimento inválida (formato esperado DD/MM/AAAA, recebido: {dados['dtNascimento']})")
            print("=" * 80)
            return False
    
    print("✅ Validação básica passou")
    print("=" * 80)
    return True

def _complementar_cadastro_cliente(conversation_id, codigo_usuario, data_nascimento=None, genero=None):
    """
    Complementa o cadastro do cliente com campos que não podem ser enviados
    no endpoint de criação (/cliente/gravar), como data de nascimento e gênero.
    """
    import os
    import requests
    from store.database import update_context
    
    url = f"https://app.bellesoftware.com.br/api/release/controller/IntegracaoExterna/v1.0/cliente?codCliente={codigo_usuario}"
    
    headers = {
        "Authorization": os.getenv("LABELLE_TOKEN"),
        "Content-Type": "application/json"
    }
    
    payload = {}
    context_update = {}
    
    if data_nascimento:
        payload["dataNascimento"] = data_nascimento
        context_update["dtNascimento"] = data_nascimento
    
    if genero:
        payload["genero"] = genero
        context_update["genero"] = genero
    
    if not payload:
        print("⚠️ Nenhum dado complementar para atualizar")
        return True
    
    payload["observacao"] = "Complemento de cadastro via WhatsApp"
    
    try:
        print("=" * 80)
        print("🔄 COMPLEMENTANDO CADASTRO DO CLIENTE")
        print(f"Código do cliente: {codigo_usuario}")
        print(f"Payload: {payload}")
        print("=" * 80)
        
        response = requests.put(url, json=payload, headers=headers)
        
        if response.status_code not in [200, 204]:
            print(f"❌ Erro API complemento (status {response.status_code}): {response.text}")
            return False
        
        update_context(conversation_id, context_update)
        print("✅ Dados complementares atualizados com sucesso!")
        print("=" * 80)
        return True
    
    except Exception as e:
        print(f"❌ Erro ao complementar cadastro: {e}")
        print("=" * 80)
        return False

def _verificar_cpf_duplicado(cpf):
    """
    Verifica se o CPF já está cadastrado na API Belle.
    Retorna: (bool, str|None) - (já_existe, nome_cadastrado)
    """
    headers = {'Authorization': os.getenv("LABELLE_TOKEN")}
    url = f'https://app.bellesoftware.com.br/api/release/controller/IntegracaoExterna/v1.0/cliente/listar?cpf={cpf}&id=&codEstab=1&email=&celular='
    
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        data = response.json()
        
        # API retorna um OBJETO com "codigo" quando encontra cadastro
        if isinstance(data, dict) and "codigo" in data:
            nome = data.get("nome", "")
            return True, nome
        
        # CPF não encontrado
        return False, None
        
    except Exception as e:
        print(f"⚠️ Erro ao verificar CPF: {e}")
        # Em caso de erro, assume que não existe (para não bloquear o fluxo)
        return False, None

def _criar_cadastro_na_api(conversation_id, dados):
    """Cria o cadastro chamando a API Belle."""
    print("=" * 80)
    print("🔥 DEBUG _criar_cadastro_api - INÍCIO")
    print(f"Conversation ID: {conversation_id}")
    print(f"Dados a enviar:")
    for k, v in dados.items():
        print(f"  {k}: {v}")
    
    # 🔥 VALIDAÇÃO CRÍTICA: Verifica se CPF já existe ANTES de tentar criar
    print("🔍 Verificando se CPF já está cadastrado...")
    cpf_existe, nome_cadastrado = _verificar_cpf_duplicado(dados['cpf'])
    
    if cpf_existe:
        print(f"❌ CPF já cadastrado para: {nome_cadastrado}")
        print("❌ BLOQUEANDO criação de cadastro duplicado")
        print("=" * 80)
        return False, None
    
    print("✅ CPF disponível, prosseguindo com criação...")
    
    # Monta payload para API Belle (endpoint /gravar)
    # Campos obrigatórios: nome, cpf, codEstab
    # IMPORTANTE: dtNascimento e genero NÃO são aceitos neste endpoint, serão enviados depois via PUT
    payload = {
        "nome": dados['nome'],
        "cpf": dados['cpf'],
        "codEstab": 1,
        "ddiCelular": "+55",
        "celular": dados['celular'],
        "email": dados['email'],
        "observacao": "Cadastro realizado via WhatsApp",
        "tpOrigem": "WhatsApp",
        "codOrigem": "99"
    }
    
    url = 'https://app.bellesoftware.com.br/api/release/controller/IntegracaoExterna/v1.0/cliente/gravar'
    headers = {
        'Authorization': os.getenv("LABELLE_TOKEN"),
        'Content-Type': 'application/json'
    }
    
    print(f"URL: {url}")
    print(f"Payload: {payload}")
    
    try:
        response = requests.post(url, json=payload, headers=headers)
        print(f"Status Code: {response.status_code}")
        print(f"Response: {response.text}")
        
        if response.status_code == 200 or response.status_code == 201:
            data = response.json()
            
            # 🔥 VALIDAÇÃO CRÍTICA: Verifica se a API retornou erro mesmo com status 200
            if "error" in data:
                erro_msg = data.get("error", "Erro desconhecido")
                print(f"❌ API retornou erro: {erro_msg}")
                print("=" * 80)
                
                # Verifica se é erro de CPF duplicado
                if "CPF já foi cadastrado" in erro_msg or "CPF já cadastrado" in erro_msg:
                    print("❌ ERRO CRÍTICO: CPF duplicado detectado pela API")
                    return False, None
                
                # Outros erros
                return False, None
            
            # Verifica se retornou código do usuário (sucesso real)
            if not data.get('codigo'):
                print("❌ API não retornou código do usuário")
                print(f"Resposta completa: {data}")
                print("=" * 80)
                return False, None
            
            print("✅ Cadastro criado com sucesso!")
            print(f"Resposta da API: {data}")
            print("=" * 80)
            
            # Atualiza contexto com dados do cadastro criado
            context_data = {
                "codigo_usuario": data.get('codigo'),
                "nome": dados['nome'],
                "cpf": dados['cpf'],
                "celular": dados['celular'],
                "email": dados['email'],
                "cadastro_completo": True
            }
            update_context(conversation_id, context_data)
            
            print(f"✅ Cadastro criado com sucesso! Código: {data.get('codigo')}")
            print("=" * 80)
            
            # Complementa cadastro com dtNascimento e genero (não aceitos no endpoint de criação)
            if dados.get('dtNascimento') or dados.get('genero'):
                print("🔄 Complementando cadastro com data de nascimento e gênero...")
                sucesso_complemento = _complementar_cadastro_cliente(
                    conversation_id=conversation_id,
                    codigo_usuario=data.get('codigo'),
                    data_nascimento=dados.get('dtNascimento'),
                    genero=dados.get('genero')
                )
                if not sucesso_complemento:
                    print("⚠️ Cadastro criado mas não foi possível adicionar data de nascimento e gênero")
            
            return True, "✅ <strong>Cadastro criado com sucesso!</strong>\n\nSeus dados foram registrados. 😊"
        else:
            print(f"❌ Erro na API: {response.status_code}")
            print("=" * 80)
            return False, None
            
    except Exception as e:
        print(f"❌ ERRO INESPERADO: {e}")
        import traceback
        traceback.print_exc()
        print("=" * 80)
        return False, None

def _processar_cadastro_automatico(conversation_id, messages):
    """
    Função principal que processa o cadastro automaticamente.
    
    Retorna:
        str | None: Mensagem de sucesso se o cadastro foi criado, None caso contrário
    """
    print("=" * 80)
    print("🚀 DEBUG _processar_cadastro_automatico - INÍCIO")
    print(f"Conversation ID: {conversation_id}")
    print(f"Total de mensagens: {len(messages)}")
    
    # Verifica se já tem cadastro completo no contexto
    session = get_session(conversation_id)
    context = session[2] or {}
    
    if isinstance(context, str):
        import json
        try:
            context = json.loads(context) if context.strip() else {}
        except:
            context = {}
    
    if context.get('cadastro_completo'):
        print("⚠️ Cadastro já está completo no contexto, pulando processamento")
        print("=" * 80)
        return None
    
    # Extrai dados do histórico
    dados = _extrair_dados_do_historico(messages)
    
    if not dados:
        print("⚠️ Não foi possível extrair dados do histórico")
        print("=" * 80)
        return None
    
    # Valida dados
    if not _validar_dados_basicos(dados):
        print("⚠️ Dados não passaram na validação básica")
        print("=" * 80)
        return None
    
    # Cria cadastro via API
    sucesso, mensagem = _criar_cadastro_na_api(conversation_id, dados)
    
    if sucesso:
        print("✅ Cadastro criado com sucesso via código!")
        print("=" * 80)
        return mensagem
    else:
        print("❌ Falha ao criar cadastro")
        print("=" * 80)
        return None
