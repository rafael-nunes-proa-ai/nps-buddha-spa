# 🎯 Agente NPS - Buddha Spa

Sistema automatizado de pesquisa de satisfação (NPS) via WhatsApp para coletar feedback de clientes após consultas.

---

## 📋 Descrição

O Agente NPS é responsável por:
- Receber respostas de clientes a mensagens HSM/Template
- Coletar avaliação de 1-5 sobre o profissional
- Coletar avaliação de 1-5 sobre a unidade
- Solicitar feedback textual quando necessário (notas baixas)
- Armazenar todas as avaliações no banco de dados
- Enviar link para avaliação no Google (notas altas)

---

## 🏗️ Arquitetura

```
┌─────────────────────────────────────────────────────────────┐
│                    FLUXO COMPLETO                            │
└─────────────────────────────────────────────────────────────┘

1. Unidade dispara HSM/Template
   ↓
2. Cliente responde com nota do profissional (1-5)
   ↓
3. Bot valida e armazena
   ↓
4. Bot pergunta sobre a unidade
   ↓
5. Cliente responde com nota da unidade (1-5)
   ↓
6. Bot valida e armazena
   ↓
7. SE nota_unidade <= 2: pede feedback textual
   ↓
8. Bot envia mensagem de encerramento
   ↓
9. Salva avaliação no banco
   ↓
10. Encerra sessão
```

---

## 🚀 Tecnologias

- **Python 3.10+**
- **FastAPI** - Framework web
- **PostgreSQL 15** - Banco de dados
- **Claude 3.5 Sonnet** (via AWS Bedrock) - LLM
- **Pydantic AI** - Framework de agentes
- **Docker** - Containerização

---

## 📁 Estrutura do Projeto

```
agente-nps/
├── agents/
│   ├── agente_nps.py          # Agente principal NPS
│   └── deps.py                 # Dependências compartilhadas
├── tools/
│   └── tool_nps.py             # Tools do agente NPS
├── store/
│   ├── database.py             # Funções de banco de dados
│   └── schema.sql              # Schema do banco
├── security/
│   └── auth.py                 # Autenticação da API
├── app.py                      # FastAPI application
├── docker-compose.yml          # Configuração Docker
├── Dockerfile                  # Build da aplicação
├── requirements.txt            # Dependências Python
├── .env.example                # Exemplo de variáveis de ambiente
└── README.md                   # Este arquivo
```

---

## ⚙️ Configuração

### 1. Clonar o repositório

```bash
cd agente-nps
```

### 2. Criar arquivo `.env`

```bash
cp .env.example .env
```

Edite o `.env` com suas credenciais:

```env
# Banco de dados
DB_HOST=localhost
DB_PORT=5432
DB_NAME=nps_db
DB_USER=postgres
DB_PASSWORD=postgres

# API
API_KEY=seu_api_key_secreto

# AWS Bedrock
AWS_REGION=us-east-1
AWS_ACCESS_KEY_ID=sua_access_key
AWS_SECRET_ACCESS_KEY=sua_secret_key
```

### 3. Subir com Docker

```bash
docker-compose up --build
```

A aplicação estará disponível em: `http://localhost:8082`

---

## 📊 Banco de Dados

### Tabelas

1. **`sessions`** - Sessões de conversação
2. **`messages`** - Histórico de mensagens
3. **`avaliacoes_nps`** - Avaliações coletadas

### Schema

Execute o arquivo `store/schema.sql` para criar as tabelas:

```bash
psql -U postgres -d nps_db -f store/schema.sql
```

---

## 🔌 API Endpoints

### POST `/chat`

Processa mensagens do cliente.

**Request:**
```json
{
  "conversation_id": "5511999999999",
  "message": "5",
  "phone": "5511999999999"
}
```

**Response:**
```json
{
  "response": "Lista [[5|Excelente]][[4|Bom]][[3|Regular]][[2|Ruim]][[1|Péssimo]]"
}
```

### Headers

```
Authorization: Bearer seu_api_key
Content-Type: application/json
```

---

## 🎨 Fluxo de Mensagens

### Mensagem HSM Inicial (disparada pela unidade)

```
{{nome}}, queremos saber como você se sentiu durante sua experiência 
com a profissional {{profissional}}? 

Sua opinião é essencial para refletirmos quem faz a diferença e 
também para evoluirmos onde for preciso.

Opções:
5 - Excelente
4 - Bom
3 - Regular
2 - Ruim
1 - Péssimo
```

### Respostas do Bot

**Se nota profissional = 1 ou 2:**
```
Que pena... 😕
E o que achou da nossa unidade Buddah Spa?
```

**Se nota profissional = 3, 4 ou 5:**
```
Lista [[5|Excelente]][[4|Bom]][[3|Regular]][[2|Ruim]][[1|Péssimo]]
```

**Se nota unidade = 1 ou 2:**
```
Por favor, conte o que aconteceu para que possamos entender 
melhor a situação e buscar uma solução.
```

**Encerramento (nota unidade = 1 ou 2):**
```
{{nome}}, Agradecemos por compartilhar sua experiência. 
Lamentamos que ela não tenha sido como esperado.

Seu feedback é muito importante e será analisado com atenção 
para que possamos evoluir e melhorar.

Esperamos ter a oportunidade de oferecer uma experiência melhor 
em uma próxima visita.

Até mais! 👋
```

**Encerramento (nota unidade = 3):**
```
{{nome}}, agradecemos por compartilhar sua experiência. 
Suas respostas são muito importantes e nos ajudam a cuidar de 
cada detalhe com ainda mais atenção.

Esperamos receber você novamente em breve.👋
```

**Encerramento (nota unidade = 4 ou 5):**
```
Ficamos muito felizes com isso, {{nome}}!  
Sua experiência é muito especial para nós. Se puder, que tal 
compartilhar sua opinião deixando uma avaliação no Google? 

Ela nos ajuda a continuar cuidando de cada detalhe com carinho.
https://g.page/r/CCFEE85I5qkEAE/review

Será um prazer receber você novamente em breve. Até a próxima! 🥰
```

---

## 🧪 Testes

### Testar localmente

```bash
curl -X POST http://localhost:8082/chat \
  -H "Authorization: Bearer seu_api_key" \
  -H "Content-Type: application/json" \
  -d '{
    "conversation_id": "5511999999999",
    "message": "5",
    "phone": "5511999999999"
  }'
```

---

## 📈 Análise de Dados

### Consultar avaliações

```sql
-- Todas as avaliações
SELECT * FROM avaliacoes_nps ORDER BY data_avaliacao DESC;

-- Média de notas
SELECT 
    AVG(nota_profissional) as media_profissional,
    AVG(nota_unidade) as media_unidade
FROM avaliacoes_nps;

-- Distribuição de notas
SELECT 
    nota_profissional,
    COUNT(*) as quantidade
FROM avaliacoes_nps
GROUP BY nota_profissional
ORDER BY nota_profissional DESC;

-- Avaliações com feedback
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

---

## 🚀 Deploy (AWS Lambda + RDS)

### Preparação

1. Criar RDS PostgreSQL
2. Executar `schema.sql` no RDS
3. Configurar variáveis de ambiente no Lambda
4. Build da imagem Docker
5. Push para ECR
6. Atualizar função Lambda

### Variáveis de Ambiente (Produção)

```env
DB_HOST=rds-endpoint.amazonaws.com
DB_PORT=5432
DB_NAME=nps_db
DB_USER=postgres
DB_PASSWORD=senha_segura

AWS_REGION=us-east-1
API_KEY=api_key_producao
ENV=prod
```

---

## 📝 Licença

Propriedade de Buddha Spa - Todos os direitos reservados.

---

## 👥 Contato

Para dúvidas ou suporte, entre em contato com a equipe de desenvolvimento.
