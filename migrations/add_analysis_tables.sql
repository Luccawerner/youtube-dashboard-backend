-- =====================================================
-- MIGRATION: Add Analysis Tab + Weekly Report Tables
-- Author: Claude Code
-- Date: 2024-11-05
-- Description: Adiciona 5 novas tabelas para features de análise
-- =====================================================

-- =====================================================
-- TABLE 1: keyword_analysis
-- Armazena análise de keywords extraídas dos títulos
-- Atualização: Diária (após coleta)
-- =====================================================
CREATE TABLE IF NOT EXISTS keyword_analysis (
    id BIGSERIAL PRIMARY KEY,
    keyword TEXT NOT NULL,
    period_days INTEGER NOT NULL CHECK (period_days IN (7, 15, 30)),
    frequency INTEGER NOT NULL,
    avg_views BIGINT NOT NULL,
    video_count INTEGER NOT NULL,
    analyzed_date DATE NOT NULL DEFAULT CURRENT_DATE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

    -- Índices para performance
    CONSTRAINT unique_keyword_period_date UNIQUE (keyword, period_days, analyzed_date)
);

CREATE INDEX IF NOT EXISTS idx_keyword_period ON keyword_analysis(period_days, analyzed_date);
CREATE INDEX IF NOT EXISTS idx_keyword_frequency ON keyword_analysis(frequency DESC);

-- =====================================================
-- TABLE 2: title_patterns
-- Padrões de título vencedores por subniche
-- Atualização: Diária (após coleta)
-- =====================================================
CREATE TABLE IF NOT EXISTS title_patterns (
    id BIGSERIAL PRIMARY KEY,
    subniche TEXT NOT NULL,
    period_days INTEGER NOT NULL CHECK (period_days IN (7, 15, 30)),
    pattern_structure TEXT NOT NULL,
    pattern_description TEXT,
    example_title TEXT NOT NULL,
    avg_views BIGINT NOT NULL,
    video_count INTEGER NOT NULL,
    analyzed_date DATE NOT NULL DEFAULT CURRENT_DATE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

    -- Índices para performance
    CONSTRAINT unique_pattern_subniche_period UNIQUE (subniche, pattern_structure, period_days, analyzed_date)
);

CREATE INDEX IF NOT EXISTS idx_pattern_subniche ON title_patterns(subniche, period_days, analyzed_date);
CREATE INDEX IF NOT EXISTS idx_pattern_views ON title_patterns(avg_views DESC);

-- =====================================================
-- TABLE 3: top_channels_snapshot
-- Snapshot diário dos top 5 canais por subniche
-- Atualização: Diária (após coleta)
-- =====================================================
CREATE TABLE IF NOT EXISTS top_channels_snapshot (
    id BIGSERIAL PRIMARY KEY,
    canal_id INTEGER NOT NULL REFERENCES canais_monitorados(id) ON DELETE CASCADE,
    subniche TEXT NOT NULL,
    views_30d BIGINT NOT NULL,
    subscribers_gained_30d INTEGER NOT NULL,
    rank_position INTEGER NOT NULL CHECK (rank_position BETWEEN 1 AND 5),
    snapshot_date DATE NOT NULL DEFAULT CURRENT_DATE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

    -- Índices para performance
    CONSTRAINT unique_channel_subniche_date UNIQUE (canal_id, subniche, snapshot_date)
);

CREATE INDEX IF NOT EXISTS idx_snapshot_subniche ON top_channels_snapshot(subniche, snapshot_date);
CREATE INDEX IF NOT EXISTS idx_snapshot_rank ON top_channels_snapshot(rank_position);

-- =====================================================
-- TABLE 4: gap_analysis
-- Análise de gaps (o que concorrentes fazem vs nossos)
-- Atualização: Semanal (domingos)
-- =====================================================
CREATE TABLE IF NOT EXISTS gap_analysis (
    id BIGSERIAL PRIMARY KEY,
    subniche TEXT NOT NULL,
    gap_title TEXT NOT NULL,
    gap_description TEXT,
    competitor_count INTEGER NOT NULL,
    avg_views BIGINT NOT NULL,
    example_videos JSONB,
    recommendation TEXT,
    analyzed_week_start DATE NOT NULL,
    analyzed_week_end DATE NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

    -- Índices para performance
    CONSTRAINT unique_gap_subniche_week UNIQUE (subniche, gap_title, analyzed_week_start)
);

CREATE INDEX IF NOT EXISTS idx_gap_subniche ON gap_analysis(subniche, analyzed_week_start);
CREATE INDEX IF NOT EXISTS idx_gap_views ON gap_analysis(avg_views DESC);

-- =====================================================
-- TABLE 5: weekly_reports
-- Relatórios semanais completos (JSON)
-- Atualização: Semanal (domingos 23h)
-- =====================================================
CREATE TABLE IF NOT EXISTS weekly_reports (
    id BIGSERIAL PRIMARY KEY,
    week_start DATE NOT NULL,
    week_end DATE NOT NULL,
    report_data JSONB NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

    -- Índices para performance
    CONSTRAINT unique_week_range UNIQUE (week_start, week_end)
);

CREATE INDEX IF NOT EXISTS idx_report_week ON weekly_reports(week_start DESC);

-- =====================================================
-- CLEANUP POLICY (opcional - descomentar se quiser)
-- Remove dados antigos para economizar espaço
-- =====================================================

-- COMMENT: Manter apenas últimos 90 dias de keyword_analysis
-- DELETE FROM keyword_analysis WHERE analyzed_date < CURRENT_DATE - INTERVAL '90 days';

-- COMMENT: Manter apenas últimos 90 dias de title_patterns
-- DELETE FROM title_patterns WHERE analyzed_date < CURRENT_DATE - INTERVAL '90 days';

-- COMMENT: Manter apenas últimos 90 dias de top_channels_snapshot
-- DELETE FROM top_channels_snapshot WHERE snapshot_date < CURRENT_DATE - INTERVAL '90 days';

-- COMMENT: Manter apenas últimos 12 relatórios semanais (~3 meses)
-- DELETE FROM weekly_reports WHERE week_start < CURRENT_DATE - INTERVAL '84 days';

-- =====================================================
-- FIM DA MIGRATION
-- =====================================================

-- Verificar tabelas criadas
SELECT table_name
FROM information_schema.tables
WHERE table_schema = 'public'
AND table_name IN ('keyword_analysis', 'title_patterns', 'top_channels_snapshot', 'gap_analysis', 'weekly_reports')
ORDER BY table_name;
