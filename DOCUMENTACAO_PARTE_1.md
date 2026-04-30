# DOCUMENTAÇÃO TÉCNICA - AGENTE NPS BUDDHA SPA
# PARTE 1: VISÃO GERAL, ARQUITETURA E BANCO DE DADOS
# Versão: 1.0 | Data: Abril 2026

---

## 📋 INFORMAÇÕES PARA IA

**CONTEXTO**: Esta documentação foi criada especificamente para ser consumida por uma IA em um novo chat. Contém todos os detalhes técnicos, fluxos, regras de negócio e particularidades do projeto Agente NPS.

**OBJETIVO**: Permitir que uma IA compreenda completamente o sistema de pesquisa de satisfação NPS sem precisar ler todo o código-fonte.

**ESTRUTURA**: Documentação dividida em 2 partes:
- PARTE 1: Visão Geral, Arquitetura, Stack, Banco de Dados, Fluxo Principal
- PARTE 2: Agente Detalhado, Tools, Regras de Negócio, Deploy

---

## 1. VISÃO GERAL DO SISTEMA

### 1.1 Propósito
Sistema automatizado de pesquisa de satisfação (NPS - Net Promoter Score) via WhatsApp para coletar feedback de clientes após consultas no Buddha Spa.

### 1.2 Funcionalidades Principais
- ✅ Recebe respostas de clientes a mensagens HSM/Template do WhatsApp
- ✅ Coleta avaliação de 1-5 sobre o profissional que atendeu
- ✅ Coleta avaliação de 1-5 sobre a unidade Buddha Spa
- ✅ Solicita feedback textual quando necessário (notas baixas)
- ✅ Armazena todas as avaliações em banco de dados PostgreSQL
- ✅ Envia link para avaliação no Google (notas altas)
- ✅ Encerra automaticamente a sessão após conclusão

### 1.3 Características Técnicas
- **1 agente especializado** (nps_agent)
- **6 tools** para processamento de avaliações
- **Stateful**: Contexto persistente em PostgreSQL
- **Determinístico**: Temperature 0.0 para seguir instruções rigidamente
- **Integração WhatsApp**: Via React Flow (frontend externo)
- **HSM Templates**: Mensagens pré-aprovadas pelo WhatsApp

### 1.4 Modelo de IA
- **Modelo Principal**: `us.anthropic.claude-sonnet-4-5-20250929-v1:0` (AWS Bedrock)
- **Framework**: Pydantic AI Agent
- **Temperature**: 0.0 (determinístico)
- **Max Tokens**: Default (não especificado)

---

## 2. ARQUITETURA

### 2.1 Stack Tecnológico

```
Backend:
├── FastAPI (Framework Web)
├── Pydantic AI Agent (Framework de Agentes)
├── AWS Bedrock Claude Sonnet 4.5 (LLM)
├── PostgreSQL 15 (Banco de Dados)
├── Docker + Docker Compose (Containerização)
└── Python 3.10+

Integrações:
└── React Flow Frontend (não incluído - sistema externo)

Bibliotecas Principais:
├── pydantic-ai
├── psycopg2-binary
├── boto3 (AWS SDK)
├── fastapi
├── uvicorn
└── python-dotenv
```

### 2.2 Diagrama de Fluxo

```
┌─────────────────────────────────────────────────────────────┐
│                    FLUXO COMPLETO NPS                        │
└─────────────────────────────────────────────────────────────┘

1. Unidade dispara HSM/Template WhatsApp
   ├── Variáveis: {{nome}}, {{profissional}}
   └── Opções: 5, 4, 3, 2, 1
   
2. Cliente responde com nota do profissional (1-5)
   ↓
3. Bot valida e armazena (validar_nota_profissional)
   ↓
4. Bot pergunta sobre a unidade
   ├── Se nota_prof 1-2: "Que pena... 😕"
   ├── Se nota_prof 3: "Obrigado pela sua avaliação!"
   └── Se nota_prof 4-5: "Que ótimo! 😊"
   
5. Cliente responde com nota da unidade (1-5)
   ↓
6. Bot valida e armazena (validar_nota_unidade)
   ↓
7. SE nota_unidade <= 2:
   ├── Pede feedback textual
   └── Armazena feedback
   
8. Bot envia mensagem de encerramento
   ├── Se nota_unidade 1-2: Mensagem de lamento
   ├── Se nota_unidade 3: Agradecimento
   └── Se nota_unidade 4-5: Link Google Review
   
9. Salva avaliação completa no banco (salvar_avaliacao_completa)
   ↓
10. Encerra sessão (encerrar_pesquisa)
    └── Delete session + flag finalizar_sessao
```

### 2.3 Fluxo de Requisição HTTP

```
1. POST /chat
   ├── conversation_id: str (telefone do cliente)
   ├── message: str (resposta do cliente)
   └── phone: str (opcional)
   
2. Verifica palavra de encerramento ("sair", "encerrar")
   └── Se sim → deleta sessão + retorna despedida
   
3. Ensure Session
   └── Cria sessão se não existe
   
4. Get Messages
   └── Recupera histórico do PostgreSQL
   
5. PRIMEIRA MENSAGEM (histórico vazio):
   ├── Gera opções de nota profissional automaticamente
   ├── Adiciona ao histórico
   └── Retorna JSON com opções
   
6. MENSAGENS SUBSEQUENTES:
   ├── Adiciona mensagem do usuário ao histórico
   ├── Executa nps_agent com histórico + contexto
   ├── Processa output (parse JSON se necessário)
   └── Adiciona resposta ao histórico
   
7. Return Response
   ├── response: str ou dict (JSON de opções)
   └── finalizar_sessao: bool (opcional)
```

---

## 3. ESTRUTURA DE DIRETÓRIOS

```
agente-nps/
├── agents/
│   ├── agente_nps.py          # Agente NPS (188 linhas)
│   └── deps.py                # MyDeps dataclass (31 linhas)
│
├── tools/
│   └── tool_nps.py            # 6 tools do agente (307 linhas)
│
├── store/
│   ├── database.py            # Funções PostgreSQL (292 linhas)
│   └── schema.sql             # Schema completo (76 linhas)
│
├── security/
│   └── auth.py                # Verificação API Key
│
├── db/
│   └── init.sql               # Schema básico (13 linhas)
│
├── app.py                     # FastAPI main (473 linhas)
├── utils.py                   # Funções utilitárias (6996 bytes)
├── docker-compose.yml         # Orquestração containers
├── Dockerfile                 # Build aplicação
├── requirements.txt           # Dependências Python
├── .env                       # Variáveis ambiente
├── .env.example               # Exemplo de .env
├── README.md                  # Documentação básica
└── MENSAGENS_COM_OPCOES.md    # Doc formato de opções
```

---

## 4. BANCO DE DADOS POSTGRESQL

### 4.1 Schema Completo

**Tabela: sessions**
```sql
CREATE TABLE IF NOT EXISTS sessions (
    session_id TEXT NOT NULL PRIMARY KEY,    -- Telefone do cliente
    current_agent TEXT,                      -- Sempre "nps_agent"
    context JSONB,                           -- MyDeps serializado
    last_updated TIMESTAMP WITHOUT TIME ZONE
);

CREATE INDEX IF NOT EXISTS idx_sessions_last_updated ON sessions(last_updated);
```

**Tabela: messages**
```sql
CREATE SEQUENCE IF NOT EXISTS messages_id_seq;

CREATE TABLE IF NOT EXISTS messages (
    id INTEGER NOT NULL DEFAULT nextval('messages_id_seq'::regclass) PRIMARY KEY,
    session_id TEXT,                         -- FK para sessions
    message JSONB,                           -- Pydantic AI message
    created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_messages_session_id ON messages(session_id);
CREATE INDEX IF NOT EXISTS idx_messages_created_at ON messages(created_at);
```

**Tabela: avaliacoes_nps** (específica do NPS)
```sql
CREATE TABLE IF NOT EXISTS avaliacoes_nps (
    id SERIAL PRIMARY KEY,
    session_id TEXT NOT NULL,                -- Telefone do cliente
    telefone TEXT,                           -- Telefone formatado
    nome_cliente TEXT,                       -- Nome do cliente
    profissional TEXT,                       -- Nome do profissional
    codigo_agendamento TEXT,                 -- Código do agendamento
    unidade_codigo TEXT DEFAULT '1',         -- Código da unidade
    
    -- Notas (1-5)
    nota_profissional INTEGER CHECK (nota_profissional >= 1 AND nota_profissional <= 5),
    nota_unidade INTEGER CHECK (nota_unidade >= 1 AND nota_unidade <= 5),
    
    -- Feedback textual (opcional - apenas se nota_unidade <= 2)
    feedback_texto TEXT,
    
    -- Metadados
    data_avaliacao TIMESTAMP WITHOUT TIME ZONE DEFAULT now(),
    created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT now(),
    
    -- Dados do HSM original (se disponível)
    hsm_template_id TEXT,
    hsm_metadata JSONB
);

-- Índices para análises
CREATE INDEX IF NOT EXISTS idx_avaliacoes_telefone ON avaliacoes_nps(telefone);
CREATE INDEX IF NOT EXISTS idx_avaliacoes_data ON avaliacoes_nps(data_avaliacao);
CREATE INDEX IF NOT EXISTS idx_avaliacoes_nota_profissional ON avaliacoes_nps(nota_profissional);
CREATE INDEX IF NOT EXISTS idx_avaliacoes_nota_unidade ON avaliacoes_nps(nota_unidade);
CREATE INDEX IF NOT EXISTS idx_avaliacoes_unidade ON avaliacoes_nps(unidade_codigo);
CREATE INDEX IF NOT EXISTS idx_avaliacoes_profissional ON avaliacoes_nps(profissional);
```

### 4.2 Configuração Docker

```yaml
postgres:
  image: postgres:15
  container_name: nps_postgres
  environment:
    POSTGRES_DB: nps_db
    POSTGRES_USER: postgres
    POSTGRES_PASSWORD: postgres
  ports:
    - "5435:5432"
  volumes:
    - postgres_data:/var/lib/postgresql/data
    - ./store/schema.sql:/docker-entrypoint-initdb.d/schema.sql
```

### 4.3 Funções Principais do Database

**ensure_session(session_id: str)**
```python
# Cria sessão se não existe
# Inicializa com current_agent = "nps_agent"
# Contexto inicial vazio: {}
```

**get_session(session_id: str)**
```python
# Retorna: (session_id, current_agent, context, last_updated)
# context é JSONB → dict Python
```

**add_messages(session_id: str, new_msgs: list)**
```python
# Minimiza mensagens (remove "instructions")
# Salva apenas: kind, parts, timestamp
# Converte para JSONB
```

**get_messages(session_id: str)**
```python
# Recupera histórico
# Filtra mensagens inválidas (sem parts)
# Converte JSONB → ModelMessage (Pydantic AI)
# Trata erros removendo mensagens corrompidas
# Retorna: list[ModelMessage]
```

**update_context(session_id: str, data: dict)**
```python
# Merge de contexto usando COALESCE + || (JSONB)
# Atualiza last_updated
```

**delete_session(session_id: str)**
```python
# Remove mensagens e sessão
# Usado no encerramento da pesquisa
```

**salvar_avaliacao_nps(dados: dict)**
```python
# Insere registro na tabela avaliacoes_nps
# Campos: session_id, telefone, nome_cliente, profissional,
#         codigo_agendamento, unidade_codigo, nota_profissional,
#         nota_unidade, feedback_texto, hsm_template_id, hsm_metadata
```

**cleanup_sessions(ttl_days=7, interval_hours=24)**
```python
# Thread daemon para limpeza automática
# Remove sessões > 7 dias
# Executa a cada 24 horas
```

### 4.4 Minimização de Mensagens

**Problema**: Mensagens com `instructions` causam crescimento exponencial do histórico

**Solução**: Função `_minimize_message()` remove `instructions` antes de salvar

```python
def _minimize_message(msg_dict: dict) -> dict:
    keep = ["kind", "parts", "timestamp"]
    minimized = {k: msg_dict.get(k) for k in keep if k in msg_dict}
    return minimized
```

**Motivo**: `instructions` são geradas dinamicamente pelo agente a cada execução

---

## 5. SISTEMA DE DEPENDÊNCIAS (MyDeps)

### 5.1 Estrutura Completa

```python
@dataclass
class MyDeps:
    """Dependências para o agente NPS - Pesquisa de Satisfação"""
    
    # === IDENTIFICAÇÃO (1 campo) ===
    session_id: str                        # Telefone do cliente
    
    # === DADOS DO CLIENTE (2 campos) ===
    nome: Optional[str] = None             # Nome do cliente
    telefone: Optional[str] = None         # Telefone formatado
    
    # === DADOS DO ATENDIMENTO (3 campos) ===
    profissional: Optional[str] = None     # Nome do profissional
    codigo_agendamento: Optional[str] = None  # Código do agendamento
    unidade_codigo: Optional[str] = None   # Código da unidade
    
    # === AVALIAÇÕES NPS (3 campos) ===
    nota_profissional: Optional[int] = None  # 1-5
    nota_unidade: Optional[int] = None       # 1-5
    feedback_texto: Optional[str] = None     # Feedback textual
    
    # === CONTROLE DE FLUXO (1 campo) ===
    nps_unidade: Optional[bool] = None     # Flag para exibir opções unidade
    
    # === CONTROLE DE FINALIZAÇÃO (1 campo) ===
    finalizar_sessao: Optional[bool] = None  # Flag para React Flow
    
    # === METADADOS HSM (2 campos) ===
    hsm_template_id: Optional[str] = None  # ID do template HSM
    hsm_metadata: Optional[dict] = None    # Metadados do HSM
```

**TOTAL: 13 campos**

### 5.2 Campos Críticos por Etapa

**Etapa 1 - Nota Profissional:**
- `nome` = nome do cliente (do HSM)
- `profissional` = nome do profissional (do HSM)
- `nota_profissional` = nota de 1-5

**Etapa 2 - Nota Unidade:**
- `nota_unidade` = nota de 1-5
- `nps_unidade` = True (flag para controle)

**Etapa 3 - Feedback (opcional):**
- `feedback_texto` = texto do feedback (apenas se nota_unidade <= 2)

**Etapa 4 - Finalização:**
- `finalizar_sessao` = True (para React Flow encerrar)

---

## 6. VARIÁVEIS DE AMBIENTE (.env)

```bash
# AWS Bedrock
AWS_REGION=us-east-1
AWS_ACCESS_KEY_ID=AKIA...
AWS_SECRET_ACCESS_KEY=...

# PostgreSQL
DB_HOST=postgres  # Nome do container
DB_PORT=5432
DB_NAME=nps_db
DB_USER=postgres
DB_PASSWORD=postgres

# FastAPI
PORT=8082
API_KEY=seu_api_key_secreto

# Ambiente
ENV=dev  # ou prod
```

---

## 7. DOCKER COMPOSE

```yaml
services:
  app:
    build: .
    image: nps_stack:latest
    container_name: nps_stack
    ports:
      - "8082:8082"
    env_file:
      - .env
    environment:
      PORT: 8082
      DB_HOST: postgres
      DB_NAME: nps_db
      DB_USER: postgres
      DB_PASSWORD: postgres
      DB_PORT: 5432
    depends_on:
      - postgres
    networks:
      - app_network

  postgres:
    image: postgres:15
    container_name: nps_postgres
    environment:
      POSTGRES_DB: nps_db
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: postgres
    ports:
      - "5435:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data
      - ./store/schema.sql:/docker-entrypoint-initdb.d/schema.sql
    networks:
      - app_network

volumes:
  postgres_data:

networks:
  app_network:
    driver: bridge
```

**Comandos**:
```bash
# Build e start
docker-compose up --build

# Start apenas
docker-compose up

# Stop
docker-compose down

# Stop + remove volumes
docker-compose down -v

# Logs
docker-compose logs -f app
```

---

## 8. MENSAGEM HSM INICIAL

### 8.1 Template WhatsApp

A mensagem HSM (Highly Structured Message) é disparada pela unidade Buddha Spa após a consulta do cliente. É uma mensagem pré-aprovada pelo WhatsApp com variáveis dinâmicas.

**Template:**
```
{{nome}}, queremos saber como você se sentiu durante sua experiência 
com a profissional {{profissional}}?

Sua opinião é essencial para refletirmos quem faz a diferença e 
também para evoluirmos onde for preciso.
```

**Variáveis:**
- `{{nome}}` = Nome do cliente
- `{{profissional}}` = Nome do profissional que atendeu

**Opções Interativas:**
```
5 - Excelente
4 - Bom
3 - Regular
2 - Ruim
1 - Péssimo
```

### 8.2 Contexto Inicial

Quando o HSM é disparado, o sistema externo (React Flow) cria a sessão com contexto inicial:

```json
{
  "nome": "Maria Silva",
  "profissional": "Ana Costa",
  "telefone": "5511999999999",
  "codigo_agendamento": "AGD12345",
  "unidade_codigo": "1",
  "hsm_template_id": "nps_pos_consulta_v1",
  "hsm_metadata": {
    "data_consulta": "2026-04-29",
    "tipo_terapia": "Terapia Relaxante"
  }
}
```

---

## 9. FLUXO PRINCIPAL DETALHADO

### 9.1 Primeira Mensagem (Histórico Vazio)

**Quando**: `len(history) == 0`

**Comportamento em app.py**:
```python
if len(history) == 0:
    # Busca nome do cliente e profissional do contexto
    nome_cliente = context.get('nome_cliente', 'Cliente')
    nome_profissional = context.get('nome_profissional', 'profissional')
    
    # Cria JSON de opções manualmente
    opcoes_resposta = {
        "output": {
            "generic": [
                {
                    "response_type": "option",
                    "title": f"Olá! {nome_cliente}, queremos saber como você se sentiu durante sua experiência com a profissional {nome_profissional}?\nSua opinião é essencial...",
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
    
    # Adiciona ao histórico (user + bot)
    user_message = ModelRequest(parts=[UserPromptPart(content=message)])
    add_messages(conversation_id, [user_message])
    
    bot_message = ModelResponse(parts=[TextPart(content=opcoes_resposta)])
    add_messages(conversation_id, [bot_message])
    
    return opcoes_resposta
```

**Importante**: As opções são geradas automaticamente pelo `app.py`, não pelo agente. Isso garante que a primeira interação seja sempre consistente.

### 9.2 Mensagens Subsequentes

**Quando**: `len(history) > 0`

**Comportamento**:
1. Adiciona mensagem do usuário ao histórico
2. Executa `nps_agent.run()` com histórico + contexto
3. Processa output do agente
4. Adiciona resposta ao histórico
5. Retorna resposta

---

## 10. FORMATO DE RESPOSTA (JSON de Opções)

### 10.1 Estrutura AWS Broker

O sistema usa o formato AWS Broker para opções interativas:

```json
{
  "output": {
    "generic": [
      {
        "response_type": "option",
        "title": "Texto da pergunta",
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
```

### 10.2 Parsing em app.py

O `app.py` trata diferentes formatos de output do agente:

```python
# Se output for string JSON
if isinstance(output_raw, str):
    cleaned_output = output_raw.strip()
    # Remove markdown
    if cleaned_output.startswith("```json"):
        cleaned_output = cleaned_output.replace("```json", "").replace("```", "").strip()
    
    # Parse para dict
    parsed_output = json.loads(cleaned_output)
    
    # Envolve com 'output' se não tiver
    if "output" not in parsed_output:
        output_final = {"output": parsed_output}
```

---

**FIM DA PARTE 1**

**PRÓXIMA PARTE**: Agente NPS Detalhado, Tools, Regras de Negócio, Deploy
