CREATE TABLE IF NOT EXISTS sessions (
    session_id TEXT PRIMARY KEY,
    current_agent TEXT,
    context JSONB,
    last_updated TIMESTAMP
);

CREATE TABLE IF NOT EXISTS messages (
    id SERIAL PRIMARY KEY,
    session_id TEXT,
    message JSONB,
    created_at TIMESTAMP DEFAULT NOW()
);