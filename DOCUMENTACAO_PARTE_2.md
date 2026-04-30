# DOCUMENTAÇÃO TÉCNICA - AGENTE NPS BUDDHA SPA
# PARTE 2: AGENTE, TOOLS, REGRAS E DEPLOY
# Versão: 1.0 | Data: Abril 2026

---

## 11. AGENTE NPS DETALHADO

### 11.1 Configuração

**Nome**: Não especificado (apenas nps_agent)

**Modelo**: `us.anthropic.claude-sonnet-4-5-20250929-v1:0` (Claude Sonnet 4.5)

**Settings**:
```python
model_settings={
    "temperature": 0.0  # Determinístico - segue instruções rigidamente
}
```

**Tools** (6):
- `validar_nota_profissional`
- `validar_nota_unidade`
- `armazenar_feedback`
- `salvar_avaliacao_completa`
- `encerrar_pesquisa`
- `gerar_opcoes_notas`

### 11.2 System Prompt Resumido

```
# VOCÊ É O ASSISTENTE DE PESQUISA NPS DO BUDDHA SPA

Sua função é coletar avaliações de clientes após suas consultas de forma educada e eficiente.

## 🎯 OBJETIVO
Coletar duas notas (profissional e unidade) e, quando necessário, um feedback textual.

## 📋 FLUXO DA PESQUISA

ETAPA 1 - RECEPÇÃO DA NOTA DO PROFISSIONAL:
- A primeira mensagem com opções já foi enviada automaticamente
- Cliente responderá com nota de 1 a 5
- Se não for número 1-5 → chama gerar_opcoes_notas
- Se for número válido → chama validar_nota_profissional

ETAPA 2 - PESQUISA DA UNIDADE:
⚠️ REGRA ABSOLUTA: CHAMAR A TOOL gerar_opcoes_notas - NÃO ESCREVER TEXTO!
- Se nota_prof 1-2 → gerar_opcoes_notas("Que pena... 😕\n...")
- Se nota_prof 3 → gerar_opcoes_notas("Obrigado pela sua avaliação!\n...")
- Se nota_prof 4-5 → gerar_opcoes_notas("Que ótimo! 😊\n...")

ETAPA 3 - VALIDAÇÃO DA NOTA DA UNIDADE:
- Cliente responde com nota 1-5
- Chama validar_nota_unidade

ETAPA 4 - COLETA DE FEEDBACK (apenas se nota_unidade <= 2):
- Pede feedback textual
- Chama armazenar_feedback

ETAPA 5 - ENCERRAMENTO:
- Se nota_unidade 1-2 → Mensagem de lamento
- Se nota_unidade 3 → Agradecimento
- Se nota_unidade 4-5 → Link Google Review

ETAPA 6 - FINALIZAÇÃO:
- Chama salvar_avaliacao_completa
- Chama encerrar_pesquisa

## ⚠️ REGRAS IMPORTANTES
1. SEMPRE use as tools para validar e armazenar notas
2. NÃO invente notas ou feedbacks
3. SEMPRE use gerar_opcoes_notas para exibir opções
4. Retorne APENAS o JSON gerado pela tool
5. Use o nome do cliente nas mensagens
6. Seja educado e empático
7. NÃO peça feedback se nota_unidade >= 3
8. SEMPRE finalize com as tools de salvar e encerrar
```

### 11.3 Fluxo Completo do Agente

```
ETAPA 1 - RECEPÇÃO DA NOTA DO PROFISSIONAL:

Cliente responde: "5"

Agente:
1. Verifica se é número 1-5
2. Se SIM:
   - validar_nota_profissional("5")
   - Tool retorna: "NOTA_PROFISSIONAL_VALIDA|5"
   - Prossegue para ETAPA 2
3. Se NÃO:
   - gerar_opcoes_notas(title="Por favor, escolha uma nota de 1 a 5...")
   - Retorna JSON de opções
   - Aguarda nova resposta

ETAPA 2 - PESQUISA DA UNIDADE:

Baseado em nota_profissional:

Se nota_profissional = 1 ou 2:
  - gerar_opcoes_notas(title="Que pena... 😕\nE o que achou da nossa unidade Buddah Spa?")
  - Retorna JSON de opções
  - Aguarda resposta

Se nota_profissional = 3:
  - gerar_opcoes_notas(title="Obrigado pela sua avaliação!\nE o que achou da nossa unidade Buddah Spa?")
  - Retorna JSON de opções
  - Aguarda resposta

Se nota_profissional = 4 ou 5:
  - gerar_opcoes_notas(title="Que ótimo! 😊\nE o que achou da nossa unidade Buddah Spa?")
  - Retorna JSON de opções
  - Aguarda resposta

ETAPA 3 - VALIDAÇÃO DA NOTA DA UNIDADE:

Cliente responde: "5"

Agente:
- validar_nota_unidade("5")
- Tool retorna: "NOTA_UNIDADE_VALIDA|5"
- Prossegue para ETAPA 4 ou 5

ETAPA 4 - COLETA DE FEEDBACK (apenas se nota_unidade <= 2):

Se nota_unidade = 1 ou 2:
  Agente: "Por favor, conte o que aconteceu para que possamos entender melhor a situação e buscar uma solução."
  
  Cliente responde: "O ambiente estava muito barulhento"
  
  Agente:
  - armazenar_feedback("O ambiente estava muito barulhento")
  - Tool retorna: "FEEDBACK_ARMAZENADO"
  - Prossegue para ETAPA 5

Se nota_unidade >= 3:
  - Pula para ETAPA 5 (não pede feedback)

ETAPA 5 - ENCERRAMENTO:

Se nota_unidade = 1 ou 2:
  Agente: "{{nome}}, Agradecemos por compartilhar sua experiência. 
           Lamentamos que ela não tenha sido como esperado.
           
           Seu feedback é muito importante e será analisado com atenção 
           para que possamos evoluir e melhorar.
           
           Esperamos ter a oportunidade de oferecer uma experiência melhor 
           em uma próxima visita.
           
           Até mais! 👋"

Se nota_unidade = 3:
  Agente: "{{nome}}, agradecemos por compartilhar sua experiência. 
           Suas respostas são muito importantes e nos ajudam a cuidar de 
           cada detalhe com ainda mais atenção.
           
           Esperamos receber você novamente em breve.👋"

Se nota_unidade = 4 ou 5:
  Agente: "Ficamos muito felizes com isso, {{nome}}!  
           Sua experiência é muito especial para nós. Se puder, que tal 
           compartilhar sua opinião deixando uma avaliação no Google? 
           
           Ela nos ajuda a continuar cuidando de cada detalhe com carinho.
           https://g.page/r/CCFEE85I5qkEAE/review
           
           Será um prazer receber você novamente em breve. Até a próxima! 🥰"

ETAPA 6 - FINALIZAÇÃO:

Após enviar mensagem de encerramento:
1. salvar_avaliacao_completa()
   - Salva registro na tabela avaliacoes_nps
   - Tool retorna: "AVALIACAO_SALVA"

2. encerrar_pesquisa()
   - Deleta sessão do banco
   - Seta finalizar_sessao = True
   - Tool retorna: "PESQUISA_ENCERRADA"

3. app.py detecta finalizar_sessao = True
   - Retorna: {"response": "...", "finalizar_sessao": true}
   - React Flow encerra conversa
```

---

## 12. TOOLS DETALHADAS

### 12.1 Tool 1: validar_nota_profissional

```python
@Tool
async def validar_nota_profissional(ctx: RunContext[MyDeps], nota: str) -> str:
    """
    Valida a nota dada ao profissional (1-5) e armazena no contexto.
    
    Args:
        nota: Nota de 1 a 5 (pode ser "5", "nota 5", etc)
    
    Returns:
        "NOTA_PROFISSIONAL_VALIDA|{numero}" ou mensagem de erro
    """
    conversation_id = ctx.deps.session_id
    
    # Extrai número da mensagem usando regex
    numeros = re.findall(r'\b[1-5]\b', nota)
    if numeros:
        nota_extraida = int(numeros[0])
    else:
        return "❌ Não consegui identificar a nota. Por favor, escolha uma opção de 1 a 5."
    
    # Armazena no contexto
    update_context(conversation_id, {
        "nota_profissional": nota_extraida
    })
    
    return f"NOTA_PROFISSIONAL_VALIDA|{nota_extraida}"
```

**Comportamento**:
- Aceita "5", "nota 5", "Excelente", etc
- Extrai número de 1-5 usando regex `\b[1-5]\b`
- Armazena em `ctx.deps.nota_profissional`
- Retorna string especial para o agente processar

### 12.2 Tool 2: validar_nota_unidade

```python
@Tool
async def validar_nota_unidade(ctx: RunContext[MyDeps], nota: str) -> str:
    """
    Valida a nota dada à unidade (1-5) e armazena no contexto.
    
    Args:
        nota: Nota de 1 a 5
    
    Returns:
        "NOTA_UNIDADE_VALIDA|{numero}" ou mensagem de erro
    """
    conversation_id = ctx.deps.session_id
    
    # Extrai número da mensagem
    numeros = re.findall(r'\b[1-5]\b', nota)
    if numeros:
        nota_extraida = int(numeros[0])
    else:
        return "❌ Não consegui identificar a nota. Por favor, escolha uma opção de 1 a 5."
    
    # Armazena no contexto
    update_context(conversation_id, {
        "nota_unidade": nota_extraida
    })
    
    return f"NOTA_UNIDADE_VALIDA|{nota_extraida}"
```

**Comportamento**: Idêntico a `validar_nota_profissional`, mas armazena em `ctx.deps.nota_unidade`

### 12.3 Tool 3: armazenar_feedback

```python
@Tool
async def armazenar_feedback(ctx: RunContext[MyDeps], feedback: str) -> str:
    """
    Armazena o feedback textual do cliente.
    
    Args:
        feedback: Texto do feedback
    
    Returns:
        "FEEDBACK_ARMAZENADO"
    """
    conversation_id = ctx.deps.session_id
    
    # Armazena no contexto
    update_context(conversation_id, {
        "resposta_feedback_unidade": feedback
    })
    
    return "FEEDBACK_ARMAZENADO"
```

**Comportamento**:
- Armazena feedback textual em `ctx.deps.feedback_texto`
- Usado apenas quando `nota_unidade <= 2`

### 12.4 Tool 4: salvar_avaliacao_completa

```python
@Tool
async def salvar_avaliacao_completa(ctx: RunContext[MyDeps]) -> str:
    """
    Salva a avaliação completa no banco de dados (tabela avaliacoes_nps).
    
    Returns:
        "AVALIACAO_SALVA" ou mensagem de erro
    """
    from store.database import salvar_avaliacao_nps
    
    conversation_id = ctx.deps.session_id
    
    # Busca dados completos do contexto
    session = get_session(conversation_id)
    context = session[2] if session else {}
    
    # Prepara dados para salvar
    dados = {
        "session_id": conversation_id,
        "telefone": context.get("telefone"),
        "nome_cliente": context.get("nome"),
        "profissional": context.get("profissional"),
        "codigo_agendamento": context.get("codigo_agendamento"),
        "unidade_codigo": context.get("unidade_codigo", "1"),
        "nota_profissional": context.get("nota_profissional"),
        "nota_unidade": context.get("nota_unidade"),
        "feedback_texto": context.get("resposta_feedback_unidade"),
        "hsm_template_id": context.get("hsm_template_id"),
        "hsm_metadata": context.get("hsm_metadata")
    }
    
    # Salva no banco
    try:
        salvar_avaliacao_nps(dados)
        return "AVALIACAO_SALVA"
    except Exception as e:
        return f"ERRO_AO_SALVAR|{str(e)}"
```

**Comportamento**:
- Busca todos os dados do contexto
- Insere registro na tabela `avaliacoes_nps`
- Retorna confirmação ou erro

**Implementação de salvar_avaliacao_nps**:
```python
def salvar_avaliacao_nps(dados: dict):
    conn = get_connection()
    cur = conn.cursor()
    
    cur.execute("""
        INSERT INTO avaliacoes_nps (
            session_id, telefone, nome_cliente, profissional,
            codigo_agendamento, unidade_codigo, nota_profissional,
            nota_unidade, feedback_texto, hsm_template_id, hsm_metadata
        ) VALUES (
            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
        )
    """, (
        dados["session_id"],
        dados["telefone"],
        dados["nome_cliente"],
        dados["profissional"],
        dados["codigo_agendamento"],
        dados["unidade_codigo"],
        dados["nota_profissional"],
        dados["nota_unidade"],
        dados["feedback_texto"],
        dados["hsm_template_id"],
        Json(dados["hsm_metadata"])  # JSONB
    ))
    
    conn.commit()
    cur.close()
    conn.close()
```

### 12.5 Tool 5: encerrar_pesquisa

```python
@Tool
async def encerrar_pesquisa(ctx: RunContext[MyDeps]) -> str:
    """
    Encerra a pesquisa NPS deletando a sessão.
    
    Returns:
        "PESQUISA_ENCERRADA"
    """
    conversation_id = ctx.deps.session_id
    
    # Deleta sessão do banco
    delete_session(conversation_id)
    
    # Flag para React Flow
    update_context(conversation_id, {
        "finalizar_sessao": True
    })
    
    return "PESQUISA_ENCERRADA"
```

**Comportamento**:
- Deleta sessão e mensagens do banco
- Seta flag `finalizar_sessao = True`
- React Flow detecta flag e encerra conversa

### 12.6 Tool 6: gerar_opcoes_notas

```python
@Tool
async def gerar_opcoes_notas(ctx: RunContext[MyDeps], title: str) -> dict:
    """
    Gera JSON de opções de avaliação (1-5) no formato AWS Broker.
    
    Args:
        title: Texto da pergunta
    
    Returns:
        Dict com estrutura de opções
    """
    opcoes = {
        "output": {
            "generic": [
                {
                    "response_type": "option",
                    "title": title,
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
    
    return opcoes
```

**Comportamento**:
- Gera JSON no formato AWS Broker
- Usado para exibir opções de avaliação
- Agente deve retornar APENAS o resultado desta tool, sem modificações

---

## 13. REGRAS DE NEGÓCIO CRÍTICAS

### 13.1 Validação de Notas

**Escala**: 1 a 5
- 5 = Excelente
- 4 = Bom
- 3 = Regular
- 2 = Ruim
- 1 = Péssimo

**Validação**:
- Aceita apenas números de 1 a 5
- Extrai número usando regex `\b[1-5]\b`
- Rejeita qualquer outro valor

### 13.2 Coleta de Feedback

**Regra**: Feedback textual é coletado APENAS quando `nota_unidade <= 2`

**Motivo**: Clientes insatisfeitos precisam de espaço para expressar problemas

**Implementação**:
```python
if nota_unidade <= 2:
    # Pede feedback
    "Por favor, conte o que aconteceu..."
else:
    # Pula para encerramento
    pass
```

### 13.3 Mensagens de Encerramento

**Baseadas em nota_unidade**:

**nota_unidade = 1 ou 2** (Insatisfeito):
```
{{nome}}, Agradecemos por compartilhar sua experiência. 
Lamentamos que ela não tenha sido como esperado.

Seu feedback é muito importante e será analisado com atenção 
para que possamos evoluir e melhorar.

Esperamos ter a oportunidade de oferecer uma experiência melhor 
em uma próxima visita.

Até mais! 👋
```

**nota_unidade = 3** (Neutro):
```
{{nome}}, agradecemos por compartilhar sua experiência. 
Suas respostas são muito importantes e nos ajudam a cuidar de 
cada detalhe com ainda mais atenção.

Esperamos receber você novamente em breve.👋
```

**nota_unidade = 4 ou 5** (Satisfeito):
```
Ficamos muito felizes com isso, {{nome}}!  
Sua experiência é muito especial para nós. Se puder, que tal 
compartilhar sua opinião deixando uma avaliação no Google? 

Ela nos ajuda a continuar cuidando de cada detalhe com carinho.
https://g.page/r/CCFEE85I5qkEAE/review

Será um prazer receber você novamente em breve. Até a próxima! 🥰
```

### 13.4 Link Google Review

**URL**: `https://g.page/r/CCFEE85I5qkEAE/review`

**Quando enviar**: Apenas quando `nota_unidade >= 4`

**Motivo**: Clientes satisfeitos são mais propensos a deixar avaliações positivas

### 13.5 Encerramento de Sessão

**Palavras-chave manuais**:
- "sair"
- "encerrar"

**Implementação em app.py**:
```python
if message.lower() in ["sair", "encerrar"]:
    delete_session(conversation_id)
    return {
        "response": "Obrigado por participar da nossa pesquisa de satisfação! 😊\nSua opinião é muito importante para nós!",
        "finalizar_sessao": True
    }
```

**Encerramento automático**:
- Tool `encerrar_pesquisa()` deleta sessão
- Seta `finalizar_sessao = True`
- React Flow detecta flag e encerra conversa

---

## 14. ANÁLISE DE DADOS

### 14.1 Consultas SQL Úteis

**Todas as avaliações**:
```sql
SELECT * FROM avaliacoes_nps 
ORDER BY data_avaliacao DESC;
```

**Média de notas**:
```sql
SELECT 
    AVG(nota_profissional) as media_profissional,
    AVG(nota_unidade) as media_unidade
FROM avaliacoes_nps;
```

**Distribuição de notas do profissional**:
```sql
SELECT 
    nota_profissional,
    COUNT(*) as quantidade,
    ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER (), 2) as percentual
FROM avaliacoes_nps
GROUP BY nota_profissional
ORDER BY nota_profissional DESC;
```

**Distribuição de notas da unidade**:
```sql
SELECT 
    nota_unidade,
    COUNT(*) as quantidade,
    ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER (), 2) as percentual
FROM avaliacoes_nps
GROUP BY nota_unidade
ORDER BY nota_unidade DESC;
```

**Avaliações com feedback (notas baixas)**:
```sql
SELECT 
    nome_cliente,
    profissional,
    nota_profissional,
    nota_unidade,
    feedback_texto,
    data_avaliacao
FROM avaliacoes_nps
WHERE feedback_texto IS NOT NULL
ORDER BY data_avaliacao DESC;
```

**Avaliações por profissional**:
```sql
SELECT 
    profissional,
    COUNT(*) as total_avaliacoes,
    AVG(nota_profissional) as media_nota,
    COUNT(CASE WHEN nota_profissional >= 4 THEN 1 END) as avaliacoes_positivas,
    COUNT(CASE WHEN nota_profissional <= 2 THEN 1 END) as avaliacoes_negativas
FROM avaliacoes_nps
GROUP BY profissional
ORDER BY media_nota DESC;
```

**Avaliações por unidade**:
```sql
SELECT 
    unidade_codigo,
    COUNT(*) as total_avaliacoes,
    AVG(nota_unidade) as media_nota,
    COUNT(CASE WHEN nota_unidade >= 4 THEN 1 END) as avaliacoes_positivas,
    COUNT(CASE WHEN nota_unidade <= 2 THEN 1 END) as avaliacoes_negativas
FROM avaliacoes_nps
GROUP BY unidade_codigo
ORDER BY media_nota DESC;
```

**NPS Score (Net Promoter Score)**:
```sql
SELECT 
    COUNT(CASE WHEN nota_unidade >= 4 THEN 1 END) * 100.0 / COUNT(*) as promotores_pct,
    COUNT(CASE WHEN nota_unidade <= 2 THEN 1 END) * 100.0 / COUNT(*) as detratores_pct,
    (COUNT(CASE WHEN nota_unidade >= 4 THEN 1 END) - 
     COUNT(CASE WHEN nota_unidade <= 2 THEN 1 END)) * 100.0 / COUNT(*) as nps_score
FROM avaliacoes_nps;
```

---

## 15. DEPLOY E CONFIGURAÇÃO

### 15.1 Variáveis de Ambiente

**Desenvolvimento (.env)**:
```bash
# AWS Bedrock
AWS_REGION=us-east-1
AWS_ACCESS_KEY_ID=AKIA...
AWS_SECRET_ACCESS_KEY=...

# PostgreSQL
DB_HOST=postgres
DB_PORT=5432
DB_NAME=nps_db
DB_USER=postgres
DB_PASSWORD=postgres

# FastAPI
PORT=8082
API_KEY=dev_api_key_123

# Ambiente
ENV=dev
```

**Produção**:
```bash
# AWS Bedrock
AWS_REGION=us-east-1
AWS_ACCESS_KEY_ID=AKIA...
AWS_SECRET_ACCESS_KEY=...

# PostgreSQL (RDS)
DB_HOST=rds-endpoint.amazonaws.com
DB_PORT=5432
DB_NAME=nps_db
DB_USER=postgres
DB_PASSWORD=senha_segura_producao

# FastAPI
PORT=8082
API_KEY=prod_api_key_seguro

# Ambiente
ENV=prod
```

### 15.2 Docker Build

```bash
# Build
docker-compose build

# Start
docker-compose up -d

# Logs
docker-compose logs -f app

# Stop
docker-compose down

# Rebuild completo
docker-compose down -v
docker-compose build --no-cache
docker-compose up -d
```

### 15.3 Dockerfile

```dockerfile
FROM python:3.10-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8082"]
```

### 15.4 Endpoints FastAPI

**GET /**
```
Response: {"service": "NPS Buddha Spa", "status": "running"}
```

**POST /chat**
```
Headers:
  Authorization: Bearer {API_KEY}
  Content-Type: application/json

Body:
{
  "conversation_id": "5511999999999",
  "message": "5",
  "phone": "5511999999999"
}

Response:
{
  "response": "...",
  "finalizar_sessao": false
}

ou

{
  "output": {
    "generic": [
      {
        "response_type": "option",
        "title": "...",
        "options": [...]
      }
    ]
  }
}
```

### 15.5 Autenticação

```python
# security/auth.py
from fastapi import Header, HTTPException
import os

def verificar_api_key(authorization: str = Header(...)):
    """Verifica API Key no header Authorization"""
    expected_key = os.getenv("API_KEY")
    
    # Remove "Bearer " se presente
    if authorization.startswith("Bearer "):
        api_key = authorization[7:]
    else:
        api_key = authorization
    
    if api_key != expected_key:
        raise HTTPException(status_code=401, detail="Invalid API Key")
    
    return api_key

# Uso em app.py
@app.post("/chat", dependencies=[Depends(verificar_api_key)])
async def post_chat(req: ChatRequest):
    ...
```

---

## 16. DEBUGGING E LOGS

### 16.1 Logs Importantes

```python
# Início de requisição
print(f"📨 NPS - Nova mensagem")
print(f"Conversation ID: {conversation_id}")
print(f"Mensagem: {message}")
print(f"Histórico: {len(history)} mensagens")

# Primeira mensagem
print("🎯 PRIMEIRA MENSAGEM - Retornando opções automaticamente")

# Tool execution
print(f"🔍 TOOL: validar_nota_profissional")
print(f"Nota recebida: {nota}")
print(f"✅ Nota profissional armazenada: {nota_extraida}")

# Encerramento
print("🔴 FINALIZAR_SESSAO - PALAVRA DE ENCERRAMENTO DETECTADA")
print("🗑️  Deletando sessão do banco de dados...")
print("✅ CONFIRMADO: Sessão deletada com sucesso")
```

### 16.2 Debugging Context

```python
# Ver contexto atual
session = get_session(session_id)
context = session[2]  # JSONB
print(json.dumps(context, indent=2))

# Ver histórico
messages = get_messages(session_id)
for msg in messages:
    print(f"{msg.kind}: {msg.parts}")
```

### 16.3 Problemas Comuns

**Problema**: Agente não gera opções
**Solução**: Verificar se tool `gerar_opcoes_notas` está sendo chamada corretamente

**Problema**: Contexto não persiste
**Solução**: Verificar se `update_context()` está sendo chamado nas tools

**Problema**: Sessão não encerra
**Solução**: Verificar se `encerrar_pesquisa()` está sendo chamada e se `delete_session()` executou

**Problema**: Avaliação não salva no banco
**Solução**: Verificar se `salvar_avaliacao_completa()` foi chamada antes de `encerrar_pesquisa()`

---

## 17. FLUXO COMPLETO EXEMPLO

```
1. Unidade dispara HSM WhatsApp
   Contexto inicial: {nome: "Maria", profissional: "Ana", telefone: "5511999999999"}

2. POST /chat {"conversation_id": "5511999999999", "message": "Olá"}
   → Histórico vazio (primeira mensagem)
   → app.py gera opções automaticamente
   → Response: {"output": {"generic": [{"response_type": "option", ...}]}}

3. POST /chat {"conversation_id": "5511999999999", "message": "5"}
   → nps_agent executa
   → validar_nota_profissional("5")
   → nota_profissional = 5 armazenada
   → gerar_opcoes_notas("Que ótimo! 😊\nE o que achou da nossa unidade Buddah Spa?")
   → Response: {"output": {"generic": [...]}}

4. POST /chat {"conversation_id": "5511999999999", "message": "5"}
   → nps_agent executa
   → validar_nota_unidade("5")
   → nota_unidade = 5 armazenada
   → Agente: "Ficamos muito felizes com isso, Maria!... [link Google]"
   → salvar_avaliacao_completa()
   → Registro inserido na tabela avaliacoes_nps
   → encerrar_pesquisa()
   → Sessão deletada
   → Response: {"response": "Ficamos muito felizes...", "finalizar_sessao": true}

5. React Flow detecta finalizar_sessao = true
   → Encerra conversa
```

---

## 18. PARTICULARIDADES TÉCNICAS

### 18.1 Primeira Mensagem Automática

**Particularidade**: A primeira mensagem com opções é gerada pelo `app.py`, não pelo agente.

**Motivo**: Garantir consistência e evitar que o agente precise "adivinhar" o formato correto na primeira interação.

**Implementação**:
```python
if len(history) == 0:
    # Gera opções manualmente
    opcoes_resposta = {...}
    # Adiciona ao histórico
    add_messages(conversation_id, [user_message, bot_message])
    return opcoes_resposta
```

### 18.2 Temperature 0.0

**Particularidade**: O agente usa temperature 0.0 (determinístico).

**Motivo**: Pesquisa NPS requer seguir instruções rigidamente, sem criatividade ou variação.

**Efeito**: Respostas sempre consistentes e previsíveis.

### 18.3 Minimização de Mensagens

**Particularidade**: Mensagens são minimizadas antes de salvar no banco.

**Implementação**: Remove campo `instructions` para evitar crescimento exponencial do histórico.

### 18.4 Cleanup Automático

**Particularidade**: Thread daemon limpa sessões antigas automaticamente.

**Configuração**: Remove sessões > 7 dias a cada 24 horas.

**Inicialização**:
```python
@app.on_event("startup")
async def startup_event():
    cleanup_thread = threading.Thread(
        target=cleanup_sessions,
        args=(7, 24),
        daemon=True
    )
    cleanup_thread.start()
```

---

**FIM DA DOCUMENTAÇÃO COMPLETA**

**RESUMO**:
- **PARTE 1**: Visão Geral, Arquitetura, Stack, Banco de Dados, Fluxo Principal
- **PARTE 2**: Agente NPS Detalhado, 6 Tools, Regras de Negócio, Análise de Dados, Deploy

**TOTAL**: 2 arquivos markdown com documentação completa para consumo por IA
