# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Project Is

A WhatsApp chatbot system for NPS (Net Promoter Score) surveys and appointment management at Buddha Spa. Built with FastAPI + Pydantic AI, it receives messages from a React Flow frontend and routes them to the appropriate AI agent.

## Running the Project

**Local (without Docker):**
```bash
pip install -r requirements.txt
python app.py
# Server on http://localhost:8082
```

**Docker (recommended):**
```bash
docker-compose up --build
# App: http://localhost:8082 | PostgreSQL: localhost:5435
```

**Manual API test:**
```bash
curl -X POST http://localhost:8082/chat \
  -H "X-API-KEY: seu_api_key_secreto" \
  -H "Content-Type: application/json" \
  -d '{"conversation_id": "5511999999999", "message": "5", "phone": "5511999999999", "tituloHSM": "nps_buddha"}'
```

There is no automated test suite. Testing is done by hitting the `/chat` endpoint manually.

## Architecture

### Multi-Agent Routing

The single `POST /chat` endpoint routes incoming messages to one of three Pydantic AI agents based on the `tituloHSM` field:

| `tituloHSM` value | Agent file | Purpose |
|---|---|---|
| `nps_buddha` | `agents/agente_nps.py` | Collects therapist + unit ratings (1-5) and optional text feedback |
| `confirmacao_buddha_v3` | `agents/agente_confirmacao.py` | Handles SIM/NÃO appointment confirmation with reschedule/cancel options |
| `no_show_sem_consumo_voucher` | `agents/agente_no_show.py` | Handles no-shows and reschedule offers |
| *(missing/other)* | `agents/agente_nps.py` | Fallback to NPS agent |

All agents use `claude-sonnet-4-5` via AWS Bedrock at temperature 0.1 for deterministic behavior.

### State Management

Conversation state lives entirely in PostgreSQL, not in agent memory:

- `sessions` table: holds a `context` JSONB column with flags like `botao_profissional`, `botao_unidade`, `nota_profissional_coletada`, etc.
- `messages` table: stores Pydantic AI message history in JSONB (without system prompts — those are injected per-request from `deps.py`)
- `avaliacoes_nps` table: stores completed NPS evaluations

The flow per request in `app.py`:
1. Ensure session exists in DB
2. Load message history
3. Select agent by `tituloHSM`
4. Build `MyDeps` (defined in `agents/deps.py`) with session context
5. Run agent with history
6. Parse response — extract JSON flags if present
7. Persist new messages (without system prompt entries)
8. Return response text + UI flags

### UI Button Flags

Agent tools in `tools/` update context flags that control button display in the React Flow frontend. For example, after the NPS agent collects the therapist rating, it sets `botao_unidade: true` so the frontend renders unit-rating buttons. These flags are returned in the HTTP response alongside the text message.

### `deps.py` Pattern

`MyDeps` is a dataclass passed to all agents as runtime context. It carries:
- `session_id`, `phone`, `client_name`
- The full `context` dict (JSONB from DB)
- A DB connection for tools to read/write state

Tools access it via `ctx.deps` in Pydantic AI's tool call signature.

## Environment Variables

Copy `.env.example` to `.env`. Key variables:

```
DB_HOST / DB_PORT / DB_NAME / DB_USER / DB_PASSWORD  # PostgreSQL
API_KEY          # Required in X-API-KEY header for all requests
AWS_REGION / AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY  # Bedrock access
PORT=8082
```

## Key Patterns to Follow

- **Adding a new agent**: create `agents/agente_X.py` + `tools/tool_X.py`, add a routing branch in `app.py` keyed on a new `tituloHSM` value, and add any new context flags to `store/schema.sql`.
- **Tools mutate context then return**: each tool function updates `ctx.deps.context` in memory and writes to the DB, then returns a string the agent uses to decide its next message.
- **System prompts are never persisted**: `app.py` strips `SystemPromptPart` entries before saving to the `messages` table. Do not change this — it keeps the DB lean and lets prompts be updated without migrating history.
- **Session cleanup**: a background thread in `app.py` purges sessions older than 7 days.
