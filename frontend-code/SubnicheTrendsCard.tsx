import React, { useState, useEffect } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { TrendingUp, TrendingDown, Minus } from 'lucide-react';

// Cores dos subnichos (25% opacity para background)
const SUBNICHE_COLORS: Record<string, string> = {
  'Contos Familiares': '#F97316',
  'Terror': '#DC2626',
  'Histórias Sombrias': '#7C3AED',
  'Histórias Aleatórias': '#DB2777',
  'Relatos de Guerra': '#059669',
  'Stickman': '#2563EB',
  'Antiguidade': '#D97706',
  'Histórias Motivacionais': '#65A30D',
  'Mistérios': '#4F46E5',
  'Pessoas Desaparecidas': '#0284C7',
  'Psicologia & Mindset': '#0D9488',
};

interface SubnicheTrend {
  subnicho: string;
  total_videos: number;
  avg_views: number;
  engagement_rate: number;
  trend_percent: number;
  period_days: number;
}

interface TrendsData {
  '7d': SubnicheTrend[];
  '15d': SubnicheTrend[];
  '30d': SubnicheTrend[];
}

type SortColumn = 'subnicho' | 'total_videos' | 'avg_views' | 'trend_percent' | 'engagement_rate';
type SortDirection = 'asc' | 'desc' | null;

export function SubnicheTrendsCard() {
  const [trendsData, setTrendsData] = useState<TrendsData | null>(null);
  const [selectedPeriod, setSelectedPeriod] = useState<'7d' | '15d' | '30d'>('7d');
  const [sortColumn, setSortColumn] = useState<SortColumn>('avg_views');
  const [sortDirection, setSortDirection] = useState<SortDirection>('desc');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchTrends();
  }, []);

  const fetchTrends = async () => {
    try {
      setLoading(true);
      const response = await fetch('/api/analysis/subniche-trends');
      const result = await response.json();

      if (result.success) {
        setTrendsData(result.data);
      } else {
        setError('Erro ao carregar tendências');
      }
    } catch (err) {
      setError('Erro ao conectar com o servidor');
    } finally {
      setLoading(false);
    }
  };

  const getCurrentTrends = (): SubnicheTrend[] => {
    if (!trendsData) return [];
    return trendsData[selectedPeriod] || [];
  };

  const handleSort = (column: SortColumn) => {
    if (sortColumn === column) {
      // Ciclo: desc → asc → null (padrão)
      if (sortDirection === 'desc') {
        setSortDirection('asc');
      } else if (sortDirection === 'asc') {
        setSortDirection(null);
        setSortColumn('avg_views'); // Volta ao padrão
      }
    } else {
      setSortColumn(column);
      setSortDirection('desc');
    }
  };

  const getSortedTrends = (): SubnicheTrend[] => {
    const trends = [...getCurrentTrends()];

    if (sortDirection === null) {
      // Padrão: avg_views desc
      return trends.sort((a, b) => b.avg_views - a.avg_views);
    }

    return trends.sort((a, b) => {
      let aValue: any = a[sortColumn];
      let bValue: any = b[sortColumn];

      // Para subnicho, ordenar alfabeticamente
      if (sortColumn === 'subnicho') {
        aValue = aValue.toLowerCase();
        bValue = bValue.toLowerCase();
        return sortDirection === 'desc'
          ? bValue.localeCompare(aValue)
          : aValue.localeCompare(bValue);
      }

      // Para números, ordenar numericamente
      if (sortDirection === 'desc') {
        return (bValue || 0) - (aValue || 0);
      } else {
        return (aValue || 0) - (bValue || 0);
      }
    });
  };

  const formatNumber = (num: number): string => {
    if (num >= 1000000) {
      return (num / 1000000).toFixed(1) + 'M';
    } else if (num >= 1000) {
      return (num / 1000).toFixed(1) + 'k';
    }
    return num.toString();
  };

  const getTrendIcon = (percent: number) => {
    if (percent > 5) return <TrendingUp className="w-4 h-4 text-green-500" />;
    if (percent < -5) return <TrendingDown className="w-4 h-4 text-red-500" />;
    return <Minus className="w-4 h-4 text-gray-500" />;
  };

  const getTrendText = (percent: number): string => {
    if (percent > 0) return `+${percent.toFixed(1)}%`;
    return `${percent.toFixed(1)}%`;
  };

  const getSortIcon = (column: SortColumn) => {
    if (sortColumn !== column || sortDirection === null) return '⬍';
    return sortDirection === 'desc' ? '🔽' : '🔼';
  };

  if (loading) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>📊 Tendências por Subniche</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex items-center justify-center p-8">
            <div className="text-gray-500">Carregando...</div>
          </div>
        </CardContent>
      </Card>
    );
  }

  if (error) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>📊 Tendências por Subniche</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex items-center justify-center p-8 text-red-500">{error}</div>
        </CardContent>
      </Card>
    );
  }

  const sortedTrends = getSortedTrends();

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between">
        <CardTitle>📊 Tendências por Subniche</CardTitle>
        <div className="flex gap-2">
          {(['7d', '15d', '30d'] as const).map((period) => (
            <button
              key={period}
              onClick={() => setSelectedPeriod(period)}
              className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
                selectedPeriod === period
                  ? 'bg-primary text-white'
                  : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
              }`}
            >
              {period === '7d' ? '7 dias' : period === '15d' ? '15 dias' : '30 dias'}
            </button>
          ))}
        </div>
      </CardHeader>
      <CardContent>
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr className="border-b">
                <th
                  onClick={() => handleSort('subnicho')}
                  className="text-left p-3 cursor-pointer hover:bg-gray-50 transition-colors"
                >
                  <div className="flex items-center gap-2">
                    <span className="font-semibold">Subniche</span>
                    <span className="text-xs opacity-50">{getSortIcon('subnicho')}</span>
                  </div>
                </th>
                <th
                  onClick={() => handleSort('total_videos')}
                  className="text-right p-3 cursor-pointer hover:bg-gray-50 transition-colors"
                >
                  <div className="flex items-center justify-end gap-2">
                    <span className="font-semibold">Vídeos</span>
                    <span className="text-xs opacity-50">{getSortIcon('total_videos')}</span>
                  </div>
                </th>
                <th
                  onClick={() => handleSort('avg_views')}
                  className="text-right p-3 cursor-pointer hover:bg-gray-50 transition-colors"
                >
                  <div className="flex items-center justify-end gap-2">
                    <span className="font-semibold">Views Médias</span>
                    <span className="text-xs opacity-50">{getSortIcon('avg_views')}</span>
                  </div>
                </th>
                <th
                  onClick={() => handleSort('trend_percent')}
                  className="text-right p-3 cursor-pointer hover:bg-gray-50 transition-colors"
                >
                  <div className="flex items-center justify-end gap-2">
                    <span className="font-semibold">Tendência</span>
                    <span className="text-xs opacity-50">{getSortIcon('trend_percent')}</span>
                  </div>
                </th>
                <th
                  onClick={() => handleSort('engagement_rate')}
                  className="text-right p-3 cursor-pointer hover:bg-gray-50 transition-colors"
                >
                  <div className="flex items-center justify-end gap-2">
                    <span className="font-semibold">Engagement</span>
                    <span className="text-xs opacity-50">{getSortIcon('engagement_rate')}</span>
                  </div>
                </th>
              </tr>
            </thead>
            <tbody>
              {sortedTrends.map((trend) => {
                const color = SUBNICHE_COLORS[trend.subnicho] || '#6B7280';
                const backgroundColor = `${color}40`; // 25% opacity (40 in hex = 25%)

                return (
                  <tr
                    key={trend.subnicho}
                    className="border-b hover:bg-gray-50 transition-colors"
                    style={{ backgroundColor }}
                  >
                    <td className="p-3">
                      <div className="flex items-center gap-2">
                        <div
                          className="w-3 h-3 rounded-full"
                          style={{ backgroundColor: color }}
                        />
                        <span className="font-medium">{trend.subnicho}</span>
                      </div>
                    </td>
                    <td className="p-3 text-right text-gray-700">{trend.total_videos}</td>
                    <td className="p-3 text-right font-semibold">
                      {formatNumber(trend.avg_views)}
                    </td>
                    <td className="p-3 text-right">
                      <div className="flex items-center justify-end gap-2">
                        {getTrendIcon(trend.trend_percent)}
                        <span className="font-medium">{getTrendText(trend.trend_percent)}</span>
                      </div>
                    </td>
                    <td className="p-3 text-right text-gray-700">
                      {trend.engagement_rate.toFixed(2)}%
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>

        {sortedTrends.length === 0 && (
          <div className="text-center p-8 text-gray-500">
            Nenhum dado disponível para o período selecionado
          </div>
        )}
      </CardContent>
    </Card>
  );
}
