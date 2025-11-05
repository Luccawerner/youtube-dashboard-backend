// src/components/TopChannelsCarousel.tsx
import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { apiService } from '@/services/api';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { ColoredBadge } from '@/components/ui/colored-badge';
import { Skeleton } from '@/components/ui/skeleton';
import { ChevronLeft, ChevronRight, TrendingUp, Eye, UserPlus, ExternalLink } from 'lucide-react';
import { obterCorSubnicho } from '@/utils/subnichoColors';
import type { TopChannelsResponse } from '@/types/analysis';

interface TopChannelsCarouselProps {
  subniches: string[];
}

export function TopChannelsCarousel({ subniches }: TopChannelsCarouselProps) {
  const [currentSubnicheIndex, setCurrentSubnicheIndex] = useState(0);

  const currentSubniche = subniches[currentSubnicheIndex] || '';

  const { data, isLoading } = useQuery<TopChannelsResponse>({
    queryKey: ['top-channels', currentSubniche],
    queryFn: () => apiService.getTopChannels(currentSubniche),
    enabled: !!currentSubniche,
    staleTime: 5 * 60 * 1000,
  });

  const handlePrevious = () => {
    setCurrentSubnicheIndex((prev) => (prev > 0 ? prev - 1 : subniches.length - 1));
  };

  const handleNext = () => {
    setCurrentSubnicheIndex((prev) => (prev < subniches.length - 1 ? prev + 1 : 0));
  };

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

  const handleOpenChannel = (url: string) => {
    window.open(url, '_blank', 'noopener,noreferrer');
  };

  const cores = currentSubniche ? obterCorSubnicho(currentSubniche) : null;

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <TrendingUp className="h-5 w-5 text-primary" />
          Top 5 Canais (Últimos 30 dias)
        </CardTitle>
      </CardHeader>
      <CardContent>
        {/* Carousel Navigation */}
        <div className="flex items-center justify-between mb-6">
          <Button
            variant="outline"
            size="icon"
            onClick={handlePrevious}
            disabled={subniches.length <= 1}
          >
            <ChevronLeft className="h-4 w-4" />
          </Button>

          <div className="flex items-center gap-2">
            {currentSubniche && (
              <ColoredBadge
                text={currentSubniche}
                backgroundColor={cores?.fundo}
                borderColor={cores?.borda}
                className="text-base px-4 py-2"
              />
            )}
            <span className="text-sm text-muted-foreground">
              ({currentSubnicheIndex + 1} de {subniches.length})
            </span>
          </div>

          <Button
            variant="outline"
            size="icon"
            onClick={handleNext}
            disabled={subniches.length <= 1}
          >
            <ChevronRight className="h-4 w-4" />
          </Button>
        </div>

        {isLoading ? (
          <div className="space-y-4">
            {[...Array(5)].map((_, i) => (
              <Skeleton key={i} className="h-24 w-full" />
            ))}
          </div>
        ) : data && data.channels.length > 0 ? (
          <div className="space-y-4">
            {data.channels.map((channel) => {
              const position = channel.rank_position;
              const medal = getMedalEmoji(position);
              const channelName =
                channel.nome_canal || channel.canais_monitorados?.nome_canal || 'Canal';
              const channelUrl =
                channel.url_canal || channel.canais_monitorados?.url_canal || '';

              return (
                <Card
                  key={channel.canal_id}
                  className={`${position <= 3 ? 'border-primary/50 bg-muted/20' : ''}`}
                >
                  <CardContent className="p-4">
                    <div className="flex items-center justify-between gap-4">
                      <div className="flex items-center gap-3 flex-1 min-w-0">
                        <span className="text-2xl font-bold flex-shrink-0">{medal || `${position}º`}</span>

                        <div className="flex-1 min-w-0">
                          <div className="font-semibold text-lg truncate mb-2">
                            {channelName}
                          </div>

                          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-sm">
                            <div className="flex items-center gap-2">
                              <Eye className="h-4 w-4 text-muted-foreground flex-shrink-0" />
                              <span className="font-semibold">
                                {formatNumber(channel.views_30d)}
                              </span>
                              <span className="text-muted-foreground">views</span>
                            </div>

                            <div className="flex items-center gap-2">
                              <UserPlus className="h-4 w-4 text-muted-foreground flex-shrink-0" />
                              <span className="font-semibold">
                                +{formatNumber(channel.subscribers_gained_30d)}
                              </span>
                              <span className="text-muted-foreground">inscritos</span>
                            </div>
                          </div>
                        </div>
                      </div>

                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => handleOpenChannel(channelUrl)}
                        disabled={!channelUrl}
                        className="flex-shrink-0"
                      >
                        <ExternalLink className="h-4 w-4 mr-2" />
                        <span className="hidden sm:inline">Ir para o canal</span>
                        <span className="sm:hidden">Canal</span>
                      </Button>
                    </div>
                  </CardContent>
                </Card>
              );
            })}
          </div>
        ) : (
          <div className="text-center py-8 text-muted-foreground">
            Nenhum canal encontrado para {currentSubniche} nos últimos 30 dias.
          </div>
        )}

        {data && data.channels.length > 0 && (
          <div className="mt-4 text-center text-sm text-muted-foreground">
            Baseado nas views dos últimos 30 dias
          </div>
        )}
      </CardContent>
    </Card>
  );
}
