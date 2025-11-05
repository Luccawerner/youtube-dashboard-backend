// src/components/TitlePatternsCarousel.tsx
import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { apiService } from '@/services/api';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { ColoredBadge } from '@/components/ui/colored-badge';
import { Skeleton } from '@/components/ui/skeleton';
import { ChevronLeft, ChevronRight, FileText, Eye, Video, Lightbulb } from 'lucide-react';
import { obterCorSubnicho } from '@/utils/subnichoColors';
import type { TitlePatternsResponse } from '@/types/analysis';

interface TitlePatternsCarouselProps {
  subniches: string[];
}

export function TitlePatternsCarousel({ subniches }: TitlePatternsCarouselProps) {
  const [currentSubnicheIndex, setCurrentSubnicheIndex] = useState(0);
  const [selectedPeriod, setSelectedPeriod] = useState<7 | 15 | 30>(30);

  const currentSubniche = subniches[currentSubnicheIndex] || '';

  const { data, isLoading } = useQuery<TitlePatternsResponse>({
    queryKey: ['title-patterns', currentSubniche, selectedPeriod],
    queryFn: () => apiService.getTitlePatterns(currentSubniche, selectedPeriod),
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

  const cores = currentSubniche ? obterCorSubnicho(currentSubniche) : null;

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between flex-wrap gap-4">
          <CardTitle className="flex items-center gap-2">
            <FileText className="h-5 w-5 text-primary" />
            Top 5 Padrões de Título
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
              <Skeleton key={i} className="h-32 w-full" />
            ))}
          </div>
        ) : data && data.patterns.length > 0 ? (
          <div className="space-y-4">
            {data.patterns.map((pattern, index) => {
              const position = index + 1;
              const medal = getMedalEmoji(position);

              return (
                <Card
                  key={pattern.pattern_structure}
                  className={`${position <= 3 ? 'border-primary/50 bg-muted/20' : ''}`}
                >
                  <CardContent className="p-4">
                    <div className="flex items-start gap-3">
                      <span className="text-2xl font-bold">{medal || `${position}º`}</span>

                      <div className="flex-1 space-y-3">
                        <div>
                          <div className="font-semibold text-lg mb-1">
                            {pattern.pattern_structure}
                          </div>
                          <div className="text-sm text-muted-foreground">
                            {pattern.pattern_description}
                          </div>
                        </div>

                        <div className="flex items-start gap-2 bg-muted/50 p-3 rounded-md">
                          <Lightbulb className="h-4 w-4 text-primary mt-0.5 flex-shrink-0" />
                          <div className="text-sm">
                            <span className="font-medium">Exemplo:</span>{' '}
                            <span className="italic">&quot;{pattern.example_title}&quot;</span>
                          </div>
                        </div>

                        <div className="flex items-center gap-4 flex-wrap">
                          <div className="flex items-center gap-2">
                            <Eye className="h-4 w-4 text-muted-foreground" />
                            <span className="font-semibold">
                              {formatNumber(pattern.avg_views)}
                            </span>
                            <span className="text-sm text-muted-foreground">views médias</span>
                          </div>

                          <div className="flex items-center gap-2">
                            <Video className="h-4 w-4 text-muted-foreground" />
                            <span className="font-semibold">{pattern.video_count}</span>
                            <span className="text-sm text-muted-foreground">vídeos usaram</span>
                          </div>
                        </div>
                      </div>
                    </div>
                  </CardContent>
                </Card>
              );
            })}
          </div>
        ) : (
          <div className="text-center py-8 text-muted-foreground">
            Nenhum padrão encontrado para {currentSubniche} nos últimos {selectedPeriod} dias.
          </div>
        )}

        {data && data.patterns.length > 0 && (
          <div className="mt-4 text-center text-sm text-muted-foreground">
            {data.total} padrões analisados para {currentSubniche}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
