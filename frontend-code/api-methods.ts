// Adicionar estes métodos em src/services/api.ts
// Cole no final da classe ApiService, antes do fechamento da classe

// =========================================================================
// ANALYSIS TAB - New Methods
// =========================================================================

async getSubniches(): Promise<SubnichesResponse> {
  return this.fetchApi<SubnichesResponse>('/api/analysis/subniches');
}

async getKeywords(days: 7 | 15 | 30 = 30): Promise<KeywordsResponse> {
  return this.fetchApi<KeywordsResponse>(`/api/analysis/keywords?days=${days}`);
}

async getTitlePatterns(subniche: string, days: 7 | 15 | 30 = 30): Promise<TitlePatternsResponse> {
  const encodedSubniche = encodeURIComponent(subniche);
  return this.fetchApi<TitlePatternsResponse>(`/api/analysis/title-patterns?subniche=${encodedSubniche}&days=${days}`);
}

async getTopChannels(subniche: string): Promise<TopChannelsResponse> {
  const encodedSubniche = encodeURIComponent(subniche);
  return this.fetchApi<TopChannelsResponse>(`/api/analysis/top-channels?subniche=${encodedSubniche}`);
}

async getSubnicheTrends(): Promise<SubnicheTrendsResponse> {
  return this.fetchApi<SubnicheTrendsResponse>('/api/analysis/subniche-trends');
}

// =========================================================================
// WEEKLY REPORT - New Methods
// =========================================================================

async getWeeklyReport(): Promise<WeeklyReportResponse> {
  return this.fetchApi<WeeklyReportResponse>('/api/reports/weekly/latest');
}

async generateWeeklyReport(): Promise<{ message: string; report: WeeklyReport }> {
  return this.fetchApi<{ message: string; report: WeeklyReport }>(
    '/api/reports/weekly/generate',
    { method: 'POST' }
  );
}

// =========================================================================
// IMPORTS NECESSÁRIOS (adicionar no topo do arquivo api.ts)
// =========================================================================

/*
import type {
  KeywordsResponse,
  TitlePatternsResponse,
  TopChannelsResponse,
  SubnichesResponse,
  SubnicheTrendsResponse,
  WeeklyReportResponse,
  WeeklyReport
} from '@/types/analysis';
*/

// =========================================================================
// TIPOS SUBNICHE TRENDS (adicionar em src/types/analysis.ts)
// =========================================================================

/*
export interface SubnicheTrend {
  subnicho: string;
  total_videos: number;
  avg_views: number;
  engagement_rate: number;
  trend_percent: number;
  period_days: number;
}

export interface SubnicheTrendsResponse {
  success: boolean;
  data: {
    '7d': SubnicheTrend[];
    '15d': SubnicheTrend[];
    '30d': SubnicheTrend[];
  };
  total_7d: number;
  total_15d: number;
  total_30d: number;
}
*/
