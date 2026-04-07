-- ============================================================================
-- SCHEMA DO BANCO DE DADOS - AGENTE NPS
-- ============================================================================

-- Tabela de sessões (igual aos outros projetos)
CREATE TABLE IF NOT EXISTS sessions (
    session_id TEXT NOT NULL PRIMARY KEY,
    current_agent TEXT,
    context JSONB,
    last_updated TIMESTAMP WITHOUT TIME ZONE
);

-- Tabela de mensagens (igual aos outros projetos)
CREATE SEQUENCE IF NOT EXISTS messages_id_seq;

CREATE TABLE IF NOT EXISTS messages (
    id INTEGER NOT NULL DEFAULT nextval('messages_id_seq'::regclass) PRIMARY KEY,
    session_id TEXT,
    message JSONB,
    created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT now()
);

-- Índices para melhor performance
CREATE INDEX IF NOT EXISTS idx_messages_session_id ON messages(session_id);
CREATE INDEX IF NOT EXISTS idx_messages_created_at ON messages(created_at);
CREATE INDEX IF NOT EXISTS idx_sessions_last_updated ON sessions(last_updated);

-- ============================================================================
-- TABELA ESPECÍFICA DO NPS - AVALIAÇÕES
-- ============================================================================

CREATE TABLE IF NOT EXISTS avaliacoes_nps (
    id SERIAL PRIMARY KEY,
    session_id TEXT NOT NULL,
    telefone TEXT,
    nome_cliente TEXT,
    profissional TEXT,
    codigo_agendamento TEXT,
    unidade_codigo TEXT DEFAULT '1',
    
    -- Notas (1-5)
    nota_profissional INTEGER CHECK (nota_profissional >= 1 AND nota_profissional <= 5),
    nota_unidade INTEGER CHECK (nota_unidade >= 1 AND nota_unidade <= 5),
    
    -- Feedback textual (opcional)
    feedback_texto TEXT,
    
    -- Metadados
    data_avaliacao TIMESTAMP WITHOUT TIME ZONE DEFAULT now(),
    created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT now(),
    
    -- Dados do HSM original (se disponível)
    hsm_template_id TEXT,
    hsm_metadata JSONB
);

-- Índices para análises e consultas
CREATE INDEX IF NOT EXISTS idx_avaliacoes_telefone ON avaliacoes_nps(telefone);
CREATE INDEX IF NOT EXISTS idx_avaliacoes_data ON avaliacoes_nps(data_avaliacao);
CREATE INDEX IF NOT EXISTS idx_avaliacoes_nota_profissional ON avaliacoes_nps(nota_profissional);
CREATE INDEX IF NOT EXISTS idx_avaliacoes_nota_unidade ON avaliacoes_nps(nota_unidade);
CREATE INDEX IF NOT EXISTS idx_avaliacoes_unidade ON avaliacoes_nps(unidade_codigo);
CREATE INDEX IF NOT EXISTS idx_avaliacoes_profissional ON avaliacoes_nps(profissional);

-- ============================================================================
-- COMENTÁRIOS DAS TABELAS
-- ============================================================================

COMMENT ON TABLE sessions IS 'Armazena sessões de conversação do agente NPS';
COMMENT ON TABLE messages IS 'Histórico de mensagens trocadas em cada sessão';
COMMENT ON TABLE avaliacoes_nps IS 'Avaliações de satisfação coletadas pelo agente NPS';

COMMENT ON COLUMN avaliacoes_nps.nota_profissional IS 'Nota de 1 a 5 dada ao profissional';
COMMENT ON COLUMN avaliacoes_nps.nota_unidade IS 'Nota de 1 a 5 dada à unidade Buddha Spa';
COMMENT ON COLUMN avaliacoes_nps.feedback_texto IS 'Feedback textual (coletado apenas quando nota_unidade <= 2)';
