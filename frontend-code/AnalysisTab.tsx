// src/components/AnalysisTab.tsx
import { useQuery } from '@tanstack/react-query';
import { apiService } from '@/services/api';
import { KeywordsRanking } from './KeywordsRanking';
import { TitlePatternsCarousel } from './TitlePatternsCarousel';
import { TopChannelsCarousel } from './TopChannelsCarousel';
import { Skeleton } from '@/components/ui/skeleton';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { AlertCircle } from 'lucide-react';
import type { SubnichesResponse } from '@/types/analysis';

export function AnalysisTab() {
  const { data: subnichesData, isLoading, error } = useQuery<SubnichesResponse>({
    queryKey: ['subniches'],
    queryFn: () => apiService.getSubniches(),
    staleTime: 10 * 60 * 1000, // 10 minutos
  });

  if (isLoading) {
    return (
      <div className="space-y-6">
        <Skeleton className="h-[400px] w-full" />
        <Skeleton className="h-[400px] w-full" />
        <Skeleton className="h-[400px] w-full" />
      </div>
    );
  }

  if (error) {
    return (
      <Alert variant="destructive">
        <AlertCircle className="h-4 w-4" />
        <AlertDescription>
          Erro ao carregar dados de análise. Tente recarregar a página.
        </AlertDescription>
      </Alert>
    );
  }

  const subniches = subnichesData?.subniches || [];

  if (subniches.length === 0) {
    return (
      <Alert>
        <AlertCircle className="h-4 w-4" />
        <AlertDescription>
          Nenhum subniche encontrado. Adicione canais primeiro para ver análises.
        </AlertDescription>
      </Alert>
    );
  }

  return (
    <div className="space-y-6">
      {/* Top 20 Keywords */}
      <KeywordsRanking />

      {/* Top 5 Padrões de Título */}
      <TitlePatternsCarousel subniches={subniches} />

      {/* Top 5 Canais */}
      <TopChannelsCarousel subniches={subniches} />
    </div>
  );
}
