-- Migration: Add subniche_trends_snapshot table
-- Purpose: Store pre-calculated subniche trends analysis (daily snapshot)
-- Created: 2025-01-07
-- Author: Claude Code

-- Create table for subniche trends snapshot
CREATE TABLE IF NOT EXISTS subniche_trends_snapshot (
  id SERIAL PRIMARY KEY,
  subnicho TEXT NOT NULL,
  period_days INT NOT NULL CHECK (period_days IN (7, 15, 30)),
  total_videos INT DEFAULT 0,
  avg_views BIGINT DEFAULT 0,
  engagement_rate FLOAT DEFAULT 0.0,
  trend_percent FLOAT DEFAULT 0.0,
  snapshot_date DATE DEFAULT CURRENT_DATE,
  analyzed_date DATE DEFAULT CURRENT_DATE,
  created_at TIMESTAMP DEFAULT NOW(),

  -- Ensure only one record per subniche/period/date combination
  UNIQUE(subnicho, period_days, analyzed_date)
);

-- Create indexes for better query performance
CREATE INDEX IF NOT EXISTS idx_subniche_trends_date
  ON subniche_trends_snapshot(analyzed_date);

CREATE INDEX IF NOT EXISTS idx_subniche_trends_period
  ON subniche_trends_snapshot(period_days);

CREATE INDEX IF NOT EXISTS idx_subniche_trends_subnicho
  ON subniche_trends_snapshot(subnicho);

-- Add comment to table
COMMENT ON TABLE subniche_trends_snapshot IS 'Daily snapshot of subniche trends analysis (videos, views, engagement, growth)';

-- Add comments to columns
COMMENT ON COLUMN subniche_trends_snapshot.subnicho IS 'Subniche name (one of 11 categories)';
COMMENT ON COLUMN subniche_trends_snapshot.period_days IS 'Analysis period: 7, 15, or 30 days';
COMMENT ON COLUMN subniche_trends_snapshot.total_videos IS 'Total videos published in period across all mined channels';
COMMENT ON COLUMN subniche_trends_snapshot.avg_views IS 'Average views per video in period';
COMMENT ON COLUMN subniche_trends_snapshot.engagement_rate IS 'Engagement rate: (likes + comments) / views * 100';
COMMENT ON COLUMN subniche_trends_snapshot.trend_percent IS 'Percentage growth compared to previous period';
COMMENT ON COLUMN subniche_trends_snapshot.snapshot_date IS 'Date when snapshot was taken';
COMMENT ON COLUMN subniche_trends_snapshot.analyzed_date IS 'Date used for analysis (usually same as snapshot_date)';
