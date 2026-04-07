# store/database.py
import os
import json
import psycopg2
from dotenv import load_dotenv
from fastapi.encoders import jsonable_encoder
from pydantic_ai.messages import ModelMessagesTypeAdapter
from datetime import datetime, timedelta
import time
from psycopg2.extras import Json


load_dotenv()

def get_connection():
    return psycopg2.connect(
        host=os.getenv("DB_HOST"),
        port=os.getenv("DB_PORT"),
        database=os.getenv("DB_NAME"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
    )

def ensure_session(session_id: str):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO sessions (session_id, current_agent, context, last_updated)
        VALUES (%s, %s, %s::jsonb, NOW())
        ON CONFLICT (session_id) DO NOTHING
    """, (session_id, "voucher_agent", "{}"))
    conn.commit()
    cur.close()
    conn.close()

def get_session(session_id: str):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT session_id, current_agent, context, last_updated
        FROM sessions
        WHERE session_id = %s
    """, (session_id,))
    row = cur.fetchone()
    cur.close()
    conn.close()
    return row

def _minimize_message(msg_dict: dict) -> dict:
    # Mantém apenas o essencial para replay do histórico
    # ❌ REMOVIDO "instructions" - instruções são geradas dinamicamente pelo agente
    keep = ["kind", "parts", "timestamp"]
    minimized = {k: msg_dict.get(k) for k in keep if k in msg_dict}
    return minimized

def add_messages(session_id: str, new_msgs: list):
    conn = get_connection()
    cur = conn.cursor()

    for msg in new_msgs:
        msg_json = jsonable_encoder(msg)  # ✅ converte datetime, etc
        
        # 🔥 Remove instructions antes de salvar no banco
        minimized = _minimize_message(msg_json)
        
        cur.execute(
            "INSERT INTO messages (session_id, message) VALUES (%s, %s::jsonb)",
            (session_id, json.dumps(minimized))
        )

    conn.commit()
    cur.close()
    conn.close()

def get_messages(session_id: str):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        SELECT message
        FROM messages
        WHERE session_id = %s
        ORDER BY id ASC
    """, (session_id,))
    rows = cur.fetchall()

    cur.close()
    conn.close()

    # rows = [(jsonb,), (jsonb,), ...]
    raw_messages = [r[0] for r in rows]

    # Converte dicts (JSON do banco) -> ModelMessage (pydantic_ai)
    # Produção: filtra mensagens inválidas/vazias antes de validar
    filtered = []
    for m in raw_messages:
        # m pode vir como dict (jsonb) ou string (se alguém gravou errado)
        if isinstance(m, str):
            m = m.strip()
            if not m:
                continue
            try:
                m = json.loads(m)
            except Exception:
                continue

        if not isinstance(m, dict):
            continue

        parts = m.get("parts", None)

        # Remove mensagens sem parts ou com parts vazio (causa erro no Bedrock)
        if not isinstance(parts, list) or len(parts) == 0:
            continue

        filtered.append(m)
    try:
        history = ModelMessagesTypeAdapter.validate_python(filtered)
    except Exception:
        tmp = filtered[:]
        history = []
        while tmp:
            tmp.pop()  # remove a última
            try:
                history = ModelMessagesTypeAdapter.validate_python(tmp)
                break
            except Exception:
                continue

    return history

def update_current_agent(session_id: str, agent_name: str):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        UPDATE sessions
        SET current_agent=%s, last_updated=NOW()
        WHERE session_id=%s
    """, (agent_name, session_id))
    conn.commit()
    cur.close()
    conn.close()

def update_context(session_id: str, data: dict):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        UPDATE sessions
        SET context = COALESCE(context, '{}'::jsonb) || %s::jsonb,
            last_updated = NOW()
        WHERE session_id = %s
    """, (json.dumps(data), session_id))
    conn.commit()
    cur.close()
    conn.close()

def delete_session(session_id: str):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM messages WHERE session_id=%s", (session_id,))
    cur.execute("DELETE FROM sessions WHERE session_id=%s", (session_id,))
    conn.commit()
    cur.close()
    conn.close()

def cleanup_sessions(ttl_days: int = 7, interval_hours: int = 24):
    """
    Remove sessões e mensagens antigas.
    - ttl_days: sessões com last_updated < NOW() - ttl_days serão removidas
    - interval_hours: frequência de execução
    """
    while True:
        try:
            conn = get_connection()
            cur = conn.cursor()

            # 1) apaga mensagens de sessões expiradas
            cur.execute(
                """
                DELETE FROM messages
                WHERE session_id IN (
                    SELECT session_id
                    FROM sessions
                    WHERE last_updated < NOW() - (%s || ' days')::interval
                )
                """,
                (ttl_days,)
            )

            # 2) apaga as sessões expiradas
            cur.execute(
                """
                DELETE FROM sessions
                WHERE last_updated < NOW() - (%s || ' days')::interval
                """,
                (ttl_days,)
            )

            conn.commit()
            cur.close()
            conn.close()

            time.sleep(interval_hours * 3600)

        except Exception as e:
            print(f"[CLEANUP] Error: {e}")
            time.sleep(interval_hours * 3600)