// src/components/WeeklyReportModal.tsx
import { useState, useEffect } from 'react';
import { useQuery } from '@tanstack/react-query';
import { apiService } from '@/services/api';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { ColoredBadge } from '@/components/ui/colored-badge';
import { Skeleton } from '@/components/ui/skeleton';
import { Separator } from '@/components/ui/separator';
import { ScrollArea } from '@/components/ui/scroll-area';
import {
  Trophy,
  TrendingUp,
  TrendingDown,
  Eye,
  UserPlus,
  Lightbulb,
  AlertCircle,
  X,
} from 'lucide-react';
import { obterCorSubnicho } from '@/utils/subnichoColors';
import type { WeeklyReportResponse } from '@/types/analysis';
import { format } from 'date-fns';
import { ptBR } from 'date-fns/locale';

interface WeeklyReportModalProps {
  isOpen: boolean;
  onClose: () => void;
}

export function WeeklyReportModal({ isOpen, onClose }: WeeklyReportModalProps) {
  const [hasShownPopup, setHasShownPopup] = useState(false);

  const { data, isLoading, error } = useQuery<WeeklyReportResponse>({
    queryKey: ['weekly-report'],
    queryFn: () => apiService.getWeeklyReport(),
    enabled: isOpen,
    staleTime: 30 * 60 * 1000, // 30 minutos
  });

  useEffect(() => {
    // Pop-up apenas na segunda-feira, uma vez por navegador
    const today = new Date();
    const isMonday = today.getDay() === 1;
    const popupShown = localStorage.getItem('weeklyReportPopupShown');
    const popupDate = localStorage.getItem('weeklyReportPopupDate');
    const todayStr = today.toDateString();

    if (isMonday && !hasShownPopup && popupDate !== todayStr) {
      // Mostrar popup após 4 segundos
      const timer = setTimeout(() => {
        setHasShownPopup(true);
        localStorage.setItem('weeklyReportPopupShown', 'true');
        localStorage.setItem('weeklyReportPopupDate', todayStr);
      }, 4000);

      return () => clearTimeout(timer);
    }
  }, [hasShownPopup]);

  const getMedalEmoji = (position: number): string => {
    if (position === 1) return '🥇';
    if (position === 2) return '🥈';
    if (position === 3) return '🥉';
    return '';
  };

  const formatNumber = (num: number): string => {
    if (num >= 1000000) return `${(num / 1000000).toFixed(1)}M`;
    if (num >= 1000) return `${(num / 1000).toFixed(1)}K`;
    return num.toString();
  };

  const getPriorityColor = (priority: string) => {
    switch (priority) {
      case 'urgent':
        return 'destructive';
      case 'high':
        return 'default';
      default:
        return 'secondary';
    }
  };

  const getPriorityLabel = (priority: string) => {
    switch (priority) {
      case 'urgent':
        return 'URGENTE';
      case 'high':
        return 'ALTA';
      case 'medium':
        return 'MÉDIA';
      default:
        return priority.toUpperCase();
    }
  };

  if (!isOpen) return null;

  return (
    <Dialog open={isOpen} onOpenChange={onClose}>
      <DialogContent className="max-w-4xl max-h-[90vh]">
        <DialogHeader>
          <div className="flex items-center justify-between">
            <DialogTitle className="text-2xl flex items-center gap-2">
              📊 Relatório Semanal
            </DialogTitle>
            <Button variant="ghost" size="icon" onClick={onClose}>
              <X className="h-4 w-4" />
            </Button>
          </div>
          {data && (
            <div className="text-sm text-muted-foreground">
              {format(new Date(data.week_start), 'dd MMM', { locale: ptBR })} -{' '}
              {format(new Date(data.week_end), 'dd MMM yyyy', { locale: ptBR })}
            </div>
          )}
        </DialogHeader>

        <ScrollArea className="max-h-[calc(90vh-100px)] pr-4">
          {isLoading ? (
            <div className="space-y-4">
              {[...Array(5)].map((_, i) => (
                <Skeleton key={i} className="h-32 w-full" />
              ))}
            </div>
          ) : error ? (
            <Card>
              <CardContent className="pt-6">
                <div className="flex items-center gap-2 text-destructive">
                  <AlertCircle className="h-5 w-5" />
                  <span>
                    Nenhum relatório disponível. Aguarde a geração automática (domingos 23h).
                  </span>
                </div>
              </CardContent>
            </Card>
          ) : data ? (
            <div className="space-y-6">
              {/* Top 10 Nossos Vídeos */}
              <Card>
                <CardHeader>
                  <CardTitle className="flex items-center gap-2">
                    <Trophy className="h-5 w-5 text-primary" />
                    Top 10 - Nossos Vídeos
                  </CardTitle>
                  <div className="text-sm text-muted-foreground">Últimos 7 dias</div>
                </CardHeader>
                <CardContent>
                  <div className="space-y-3">
                    {data.report_data.top_10_nossos.map((video, index) => {
                      const position = index + 1;
                      const medal = getMedalEmoji(position);

                      return (
                        <div
                          key={video.video_id}
                          className={`flex items-start gap-3 p-3 rounded-lg border ${
                            position <= 3 ? 'bg-muted/30 border-primary/50' : ''
                          }`}
                        >
                          <span className="text-lg font-bold">{medal || `${position}º`}</span>
                          <div className="flex-1 min-w-0">
                            <div className="font-medium text-sm truncate mb-2">
                              {video.titulo}
                            </div>
                            <div className="flex items-center gap-4 text-sm">
                              <div className="flex items-center gap-1">
                                <Eye className="h-3 w-3 text-muted-foreground" />
                                <span className="font-semibold">
                                  {formatNumber(video.views_7d)}
                                </span>
                              </div>
                              <div className="flex items-center gap-1">
                                <UserPlus className="h-3 w-3 text-muted-foreground" />
                                <span className="font-semibold">
                                  +{formatNumber(video.subscribers_gained_7d)}
                                </span>
                              </div>
                              <span className="text-muted-foreground truncate">
                                {video.canal_nome}
                              </span>
                            </div>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </CardContent>
              </Card>

              {/* Top 10 Vídeos Minerados */}
              <Card>
                <CardHeader>
                  <CardTitle className="flex items-center gap-2">
                    🎯 Top 10 - Vídeos Minerados
                  </CardTitle>
                  <div className="text-sm text-muted-foreground">Últimos 7 dias</div>
                </CardHeader>
                <CardContent>
                  <div className="space-y-3">
                    {data.report_data.top_10_minerados.map((video, index) => {
                      const position = index + 1;
                      const medal = getMedalEmoji(position);

                      return (
                        <div
                          key={video.video_id}
                          className={`flex items-start gap-3 p-3 rounded-lg border ${
                            position <= 3 ? 'bg-muted/30 border-primary/50' : ''
                          }`}
                        >
                          <span className="text-lg font-bold">{medal || `${position}º`}</span>
                          <div className="flex-1 min-w-0">
                            <div className="font-medium text-sm truncate mb-2">
                              {video.titulo}
                            </div>
                            <div className="flex items-center gap-4 text-sm">
                              <div className="flex items-center gap-1">
                                <Eye className="h-3 w-3 text-muted-foreground" />
                                <span className="font-semibold">
                                  {formatNumber(video.views_7d)}
                                </span>
                              </div>
                              <div className="flex items-center gap-1">
                                <UserPlus className="h-3 w-3 text-muted-foreground" />
                                <span className="font-semibold">
                                  +{formatNumber(video.subscribers_gained_7d)}
                                </span>
                              </div>
                              <span className="text-muted-foreground truncate">
                                {video.canal_nome}
                              </span>
                            </div>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </CardContent>
              </Card>

              <Separator />

              {/* Performance por Subniche */}
              <Card>
                <CardHeader>
                  <CardTitle className="flex items-center gap-2">
                    <TrendingUp className="h-5 w-5 text-primary" />
                    Performance por Subniche
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="space-y-4">
                    {data.report_data.performance_by_subniche.map((perf) => {
                      const cores = obterCorSubnicho(perf.subniche);
                      const isGrowth = perf.growth_percentage >= 0;

                      return (
                        <Card key={perf.subniche}>
                          <CardContent className="p-4">
                            <div className="space-y-3">
                              <div className="flex items-center justify-between">
                                <ColoredBadge
                                  text={perf.subniche}
                                  backgroundColor={cores.fundo}
                                  borderColor={cores.borda}
                                />
                                <div className="flex items-center gap-2">
                                  {isGrowth ? (
                                    <TrendingUp className="h-4 w-4 text-green-600" />
                                  ) : (
                                    <TrendingDown className="h-4 w-4 text-red-600" />
                                  )}
                                  <span
                                    className={`font-semibold ${
                                      isGrowth ? 'text-green-600' : 'text-red-600'
                                    }`}
                                  >
                                    {isGrowth ? '+' : ''}
                                    {perf.growth_percentage.toFixed(1)}%
                                  </span>
                                </div>
                              </div>

                              <div className="flex items-center justify-between text-sm">
                                <span className="text-muted-foreground">Última semana:</span>
                                <span className="font-semibold">
                                  {formatNumber(perf.views_current_week)} views
                                </span>
                              </div>

                              <div className="flex items-center justify-between text-sm">
                                <span className="text-muted-foreground">Semana anterior:</span>
                                <span>{formatNumber(perf.views_previous_week)} views</span>
                              </div>

                              {perf.insight && (
                                <div className="flex gap-2 bg-muted/50 p-3 rounded-md">
                                  <Lightbulb className="h-4 w-4 text-primary mt-0.5 flex-shrink-0" />
                                  <div className="text-sm">{perf.insight}</div>
                                </div>
                              )}
                            </div>
                          </CardContent>
                        </Card>
                      );
                    })}
                  </div>
                </CardContent>
              </Card>

              <Separator />

              {/* Análise de Gaps */}
              <Card>
                <CardHeader>
                  <CardTitle className="flex items-center gap-2">
                    🔍 Análise de Gaps
                  </CardTitle>
                  <div className="text-sm text-muted-foreground">
                    O que concorrentes fazem e você não
                  </div>
                </CardHeader>
                <CardContent>
                  <div className="space-y-4">
                    {Object.entries(data.report_data.gap_analysis).map(
                      ([subniche, gaps]) => {
                        const cores = obterCorSubnicho(subniche);

                        return (
                          <div key={subniche}>
                            <ColoredBadge
                              text={subniche}
                              backgroundColor={cores.fundo}
                              borderColor={cores.borda}
                              className="mb-3"
                            />
                            <div className="space-y-2 pl-4">
                              {gaps.map((gap, index) => (
                                <Card key={index}>
                                  <CardContent className="p-3">
                                    <div className="font-medium text-sm mb-2">{gap.gap_title}</div>
                                    <div className="text-sm text-muted-foreground mb-2">
                                      {gap.description}
                                    </div>
                                    <div className="flex items-center gap-4 text-xs">
                                      <span>
                                        {gap.competitor_count} concorrentes
                                      </span>
                                      <span>
                                        {formatNumber(gap.avg_views)} views médias
                                      </span>
                                    </div>
                                    {gap.recommendation && (
                                      <div className="mt-2 text-sm bg-muted/50 p-2 rounded">
                                        <Lightbulb className="h-3 w-3 inline mr-1" />
                                        {gap.recommendation}
                                      </div>
                                    )}
                                  </CardContent>
                                </Card>
                              ))}
                            </div>
                          </div>
                        );
                      }
                    )}
                  </div>
                </CardContent>
              </Card>

              <Separator />

              {/* Ações Recomendadas */}
              <Card>
                <CardHeader>
                  <CardTitle className="flex items-center gap-2">
                    ✅ Ações Recomendadas
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="space-y-3">
                    {data.report_data.recommended_actions.map((action, index) => (
                      <Card key={index}>
                        <CardContent className="p-4">
                          <div className="flex items-start gap-3">
                            <Badge variant={getPriorityColor(action.priority)} className="mt-1">
                              {getPriorityLabel(action.priority)}
                            </Badge>
                            <div className="flex-1 space-y-2">
                              <div className="font-semibold">{action.title}</div>
                              <div className="text-sm text-muted-foreground">
                                {action.description}
                              </div>
                              <div className="text-sm bg-muted/50 p-3 rounded">
                                <span className="font-medium">Ação:</span> {action.action}
                              </div>
                            </div>
                          </div>
                        </CardContent>
                      </Card>
                    ))}
                  </div>
                </CardContent>
              </Card>
            </div>
          ) : null}
        </ScrollArea>
      </DialogContent>
    </Dialog>
  );
}
