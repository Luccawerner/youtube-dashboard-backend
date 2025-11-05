// src/types/analysis.ts
// Tipos para as novas features de análise

export interface Keyword {
  keyword: string;
  frequency: number;
  avg_views: number;
  video_count: number;
}

export interface KeywordsResponse {
  period_days: number;
  total: number;
  keywords: Keyword[];
}

export interface TitlePattern {
  pattern_structure: string;
  pattern_description: string;
  example_title: string;
  avg_views: number;
  video_count: number;
}

export interface TitlePatternsResponse {
  subniche: string;
  period_days: number;
  total: number;
  patterns: TitlePattern[];
}

export interface TopChannel {
  canal_id: number;
  nome_canal: string;
  url_canal: string;
  views_30d: number;
  subscribers_gained_30d: number;
  rank_position: number;
  canais_monitorados?: {
    nome_canal: string;
    url_canal: string;
  };
}

export interface TopChannelsResponse {
  subniche: string;
  total: number;
  channels: TopChannel[];
}

export interface SubnichesResponse {
  total: number;
  subniches: string[];
}

export interface TopVideo {
  video_id: string;
  titulo: string;
  canal_nome: string;
  views_7d: number;
  subscribers_gained_7d: number;
  url_video: string;
}

export interface SubnichePerformance {
  subniche: string;
  views_current_week: number;
  views_previous_week: number;
  growth_percentage: number;
  insight: string;
}

export interface Gap {
  gap_title: string;
  description: string;
  competitor_count: number;
  avg_views: number;
  recommendation: string;
}

export interface RecommendedAction {
  priority: 'urgent' | 'high' | 'medium';
  title: string;
  description: string;
  action: string;
}

export interface WeeklyReport {
  week_start: string;
  week_end: string;
  generated_at: string;
  top_10_nossos: TopVideo[];
  top_10_minerados: TopVideo[];
  performance_by_subniche: SubnichePerformance[];
  gap_analysis: Record<string, Gap[]>;
  recommended_actions: RecommendedAction[];
}

export interface WeeklyReportResponse {
  id?: number;
  week_start: string;
  week_end: string;
  report_data: WeeklyReport;
  created_at?: string;
}
