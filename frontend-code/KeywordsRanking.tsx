// src/components/KeywordsRanking.tsx
import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { apiService } from '@/services/api';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import { Trophy, TrendingUp, Eye, Video } from 'lucide-react';
import type { KeywordsResponse } from '@/types/analysis';

export function KeywordsRanking() {
  const [selectedPeriod, setSelectedPeriod] = useState<7 | 15 | 30>(30);

  const { data, isLoading, error } = useQuery<KeywordsResponse>({
    queryKey: ['keywords', selectedPeriod],
    queryFn: () => apiService.getKeywords(selectedPeriod),
    staleTime: 5 * 60 * 1000, // 5 minutos
  });

  const getMedalEmoji = (position: number): string => {
    if (position === 1) return '🥇';
    if (position === 2) return '🥈';
    if (position === 3) return '🥉';
    return '';
  };

  const formatNumber = (num: number): string => {
    if (num >= 1000000) {
      return `${(num / 1000000).toFixed(1)}M`;
    }
    if (num >= 1000) {
      return `${(num / 1000).toFixed(1)}K`;
    }
    return num.toString();
  };

  if (error) {
    return (
      <Card>
        <CardContent className="pt-6">
          <div className="text-center text-muted-foreground">
            Erro ao carregar keywords. Tente novamente mais tarde.
          </div>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <CardTitle className="flex items-center gap-2">
            <Trophy className="h-5 w-5 text-primary" />
            Top 20 Keywords
          </CardTitle>
          <div className="flex gap-2">
            <Button
              variant={selectedPeriod === 7 ? 'default' : 'outline'}
              size="sm"
              onClick={() => setSelectedPeriod(7)}
            >
              7 dias
            </Button>
            <Button
              variant={selectedPeriod === 15 ? 'default' : 'outline'}
              size="sm"
              onClick={() => setSelectedPeriod(15)}
            >
              15 dias
            </Button>
            <Button
              variant={selectedPeriod === 30 ? 'default' : 'outline'}
              size="sm"
              onClick={() => setSelectedPeriod(30)}
            >
              30 dias
            </Button>
          </div>
        </div>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <div className="space-y-3">
            {[...Array(10)].map((_, i) => (
              <Skeleton key={i} className="h-16 w-full" />
            ))}
          </div>
        ) : data && data.keywords.length > 0 ? (
          <>
            {/* Desktop View */}
            <div className="hidden lg:block">
              <div className="space-y-2">
                {data.keywords.map((keyword, index) => {
                  const position = index + 1;
                  const medal = getMedalEmoji(position);

                  return (
                    <div
                      key={keyword.keyword}
                      className={`flex items-center justify-between p-3 rounded-lg border transition-colors hover:bg-muted/50 ${
                        position <= 3 ? 'bg-muted/30' : ''
                      }`}
                    >
                      <div className="flex items-center gap-4 flex-1">
                        <div className="flex items-center gap-2 min-w-[80px]">
                          <span className="text-lg font-semibold text-muted-foreground">
                            {medal || `${position}º`}
                          </span>
                        </div>

                        <div className="flex-1">
                          <div className="font-medium text-lg capitalize">
                            {keyword.keyword}
                          </div>
                        </div>

                        <div className="flex items-center gap-6">
                          <div className="flex items-center gap-2">
                            <Eye className="h-4 w-4 text-muted-foreground" />
                            <span className="font-semibold">
                              {formatNumber(keyword.avg_views)}
                            </span>
                            <span className="text-sm text-muted-foreground">views</span>
                          </div>

                          <div className="flex items-center gap-2">
                            <Video className="h-4 w-4 text-muted-foreground" />
                            <span className="font-semibold">{keyword.video_count}</span>
                            <span className="text-sm text-muted-foreground">vídeos</span>
                          </div>

                          <div className="flex items-center gap-2">
                            <TrendingUp className="h-4 w-4 text-muted-foreground" />
                            <Badge variant="secondary">{keyword.frequency}x</Badge>
                          </div>
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>

            {/* Mobile View */}
            <div className="lg:hidden space-y-3">
              {data.keywords.map((keyword, index) => {
                const position = index + 1;
                const medal = getMedalEmoji(position);

                return (
                  <Card
                    key={keyword.keyword}
                    className={position <= 3 ? 'border-primary/50 bg-muted/30' : ''}
                  >
                    <CardContent className="p-4">
                      <div className="flex items-start justify-between mb-3">
                        <div className="flex items-center gap-2">
                          <span className="text-lg font-bold text-muted-foreground">
                            {medal || `${position}º`}
                          </span>
                          <span className="font-medium text-lg capitalize">
                            {keyword.keyword}
                          </span>
                        </div>
                      </div>

                      <div className="grid grid-cols-3 gap-3 text-sm">
                        <div className="flex flex-col">
                          <div className="flex items-center gap-1 text-muted-foreground mb-1">
                            <Eye className="h-3 w-3" />
                            <span className="text-xs">Views</span>
                          </div>
                          <span className="font-semibold">
                            {formatNumber(keyword.avg_views)}
                          </span>
                        </div>

                        <div className="flex flex-col">
                          <div className="flex items-center gap-1 text-muted-foreground mb-1">
                            <Video className="h-3 w-3" />
                            <span className="text-xs">Vídeos</span>
                          </div>
                          <span className="font-semibold">{keyword.video_count}</span>
                        </div>

                        <div className="flex flex-col">
                          <div className="flex items-center gap-1 text-muted-foreground mb-1">
                            <TrendingUp className="h-3 w-3" />
                            <span className="text-xs">Freq.</span>
                          </div>
                          <Badge variant="secondary" className="w-fit">
                            {keyword.frequency}x
                          </Badge>
                        </div>
                      </div>
                    </CardContent>
                  </Card>
                );
              })}
            </div>

            <div className="mt-4 text-center text-sm text-muted-foreground">
              {data.total} keywords analisadas nos últimos {selectedPeriod} dias
            </div>
          </>
        ) : (
          <div className="text-center py-8 text-muted-foreground">
            Nenhuma keyword encontrada para este período.
          </div>
        )}
      </CardContent>
    </Card>
  );
}
