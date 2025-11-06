"""
report_generator.py - Gerador de Relatórios Semanais
Author: Claude Code
Date: 2024-11-05

Gera relatório semanal completo com:
- Top 10 vídeos (nossos + minerados)
- Performance por subniche
- Insights automáticos
- Gap analysis
- Ações recomendadas
"""

from datetime import datetime, timedelta
from typing import Dict, List
import json
from analyzer import Analyzer


class ReportGenerator:
    """Gerador de relatórios semanais"""

    def __init__(self, db_client):
        """
        Inicializa o gerador

        Args:
            db_client: Cliente Supabase para acesso ao banco
        """
        self.db = db_client
        self.analyzer = Analyzer(db_client)

    # =========================================================================
    # GERAÇÃO DO RELATÓRIO COMPLETO
    # =========================================================================

    def generate_weekly_report(self) -> Dict:
        """
        Gera relatório semanal completo

        Returns:
            Dict com todos os dados do relatório
        """
        print("[ReportGenerator] Gerando relatório semanal...")

        # Calcular período (última semana)
        today = datetime.now()
        week_end = today.strftime("%Y-%m-%d")
        week_start = (today - timedelta(days=7)).strftime("%Y-%m-%d")

        # Gerar todas as seções
        report = {
            'week_start': week_start,
            'week_end': week_end,
            'generated_at': datetime.now().isoformat(),
            'top_10_nossos': self._get_top_10_videos('nosso', week_start, week_end),
            'top_10_minerados': self._get_top_10_videos('minerado', week_start, week_end),
            'top_10_keywords': self._get_top_10_keywords_by_subniche(),
            'performance_by_subniche': self._get_performance_by_subniche(week_start),
            'recommended_actions': self._generate_recommendations()
        }

        # Salvar no banco
        self._save_report(report)

        print("[ReportGenerator] Relatório gerado com sucesso!")
        return report

    # =========================================================================
    # TOP 10 VÍDEOS
    # =========================================================================

    def _get_top_10_videos(self, tipo_canal: str, week_start: str, week_end: str) -> List[Dict]:
        """
        Busca top 10 vídeos ÚNICOS por tipo de canal (nossos ou minerados)

        IMPORTANTE: Agrupa por video_id para evitar duplicatas (mesmo vídeo em múltiplos dias)

        Args:
            tipo_canal: 'nosso' ou 'minerado'
            week_start: Data início da semana
            week_end: Data fim da semana

        Returns:
            Lista com top 10 vídeos ÚNICOS ordenados por views (sem repetições)
        """
        print(f"[ReportGenerator] Buscando top 10 vídeos ÚNICOS ({tipo_canal})...")

        # Buscar vídeos postados nos últimos 30 dias com 10k+ views
        cutoff_date_30d = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")

        # Query: buscar TODOS os vídeos (não limitar ainda)
        response = self.db.table("videos_historico")\
            .select("*, canais_monitorados!inner(nome_canal, tipo, id, subnicho)")\
            .eq("canais_monitorados.tipo", tipo_canal)\
            .gte("data_publicacao", cutoff_date_30d)\
            .gte("views_atuais", 10000)\
            .gte("data_coleta", week_start)\
            .lte("data_coleta", week_end)\
            .order("views_atuais", desc=True)\
            .execute()

        all_videos = response.data

        # AGRUPAR por video_id pegando registro mais recente (evita duplicatas)
        videos_dict = {}
        for video in all_videos:
            video_id = video['video_id']

            if video_id not in videos_dict:
                videos_dict[video_id] = video
            else:
                # Se já existe, pega o mais recente (data_coleta mais recente)
                if video['data_coleta'] > videos_dict[video_id]['data_coleta']:
                    videos_dict[video_id] = video

        # Converter dict para lista e ordenar por views
        unique_videos = list(videos_dict.values())
        unique_videos.sort(key=lambda x: x['views_atuais'], reverse=True)

        # Pegar top 10
        top_10 = unique_videos[:10]

        # Calcular inscritos ganhos para cada canal nos últimos 7 dias
        result = []
        for video in top_10:
            canal_id = video['canais_monitorados']['id']

            # Buscar dados do canal nos últimos 7 dias
            subs_gained = self._get_subscribers_gained(canal_id, 7)

            result.append({
                'video_id': video['video_id'],
                'titulo': video['titulo'],
                'canal_nome': video['canais_monitorados']['nome_canal'],
                'canal_id': canal_id,
                'canal_subnicho': video['canais_monitorados']['subnicho'],
                'views_atuais': video['views_atuais'],
                'likes': video.get('likes', 0),
                'duracao': video.get('duracao', 0),
                'views_7d': video['views_atuais'],
                'subscribers_gained_7d': subs_gained,
                'url_video': video.get('url_video', f"https://youtube.com/watch?v={video['video_id']}")
            })

        print(f"[ReportGenerator] {len(result)} vídeos ÚNICOS encontrados ({tipo_canal})")
        return result

    def _get_subscribers_gained(self, canal_id: int, days: int) -> int:
        """Calcula inscritos ganhos no período"""
        try:
            # Buscar snapshot atual
            current = self.db.table("dados_canais_historico")\
                .select("inscritos")\
                .eq("canal_id", canal_id)\
                .order("data_coleta", desc=True)\
                .limit(1)\
                .execute()

            # Buscar snapshot N dias atrás
            past_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
            past = self.db.table("dados_canais_historico")\
                .select("inscritos")\
                .eq("canal_id", canal_id)\
                .lte("data_coleta", past_date)\
                .order("data_coleta", desc=True)\
                .limit(1)\
                .execute()

            if current.data and past.data:
                return current.data[0]['inscritos'] - past.data[0]['inscritos']

        except Exception as e:
            print(f"[ReportGenerator] Erro ao calcular inscritos: {e}")

        return 0

    # =========================================================================
    # PERFORMANCE POR SUBNICHE
    # =========================================================================

    def _get_performance_by_subniche(self, week_start: str) -> List[Dict]:
        """
        Calcula performance por subniche (última semana vs semana anterior)

        Args:
            week_start: Data início da semana atual

        Returns:
            Lista com performance de cada subniche
        """
        print("[ReportGenerator] Calculando performance por subniche...")

        # Buscar todos os subniches ativos
        subniches_response = self.db.table("canais_monitorados")\
            .select("subnicho")\
            .eq("tipo", "nosso")\
            .eq("status", "ativo")\
            .execute()

        subniches = list(set([c['subnicho'] for c in subniches_response.data]))

        result = []
        for subniche in subniches:
            # Views última semana
            week_start_date = datetime.strptime(week_start, "%Y-%m-%d")
            week_end_date = week_start_date + timedelta(days=7)

            views_current = self._get_total_views_for_subniche(
                subniche,
                week_start_date.strftime("%Y-%m-%d"),
                week_end_date.strftime("%Y-%m-%d")
            )

            # Views semana anterior
            prev_week_start = (week_start_date - timedelta(days=7)).strftime("%Y-%m-%d")
            prev_week_end = week_start_date.strftime("%Y-%m-%d")

            views_previous = self._get_total_views_for_subniche(
                subniche,
                prev_week_start,
                prev_week_end
            )

            # Calcular crescimento %
            if views_previous > 0:
                growth_pct = ((views_current - views_previous) / views_previous) * 100
            else:
                growth_pct = 100.0 if views_current > 0 else 0.0

            # Gerar insight automático
            insight = self._generate_insight_for_subniche(subniche, growth_pct, views_current)

            # Totais por período de publicação
            total_7d = self._get_total_views_by_publication(subniche, days=7)
            total_30d = self._get_total_views_by_publication(subniche, days=30)

            result.append({
                'subniche': subniche,
                'views_current_week': views_current,
                'views_previous_week': views_previous,
                'growth_percentage': round(growth_pct, 1),
                'insight': insight,
                'total_views_7d': total_7d['total_views'],
                'video_count_7d': total_7d['video_count'],
                'total_views_30d': total_30d['total_views'],
                'video_count_30d': total_30d['video_count']
            })

        print(f"[ReportGenerator] {len(result)} subniches analisados")
        return result

    def _get_total_views_for_subniche(self, subniche: str, date_start: str, date_end: str) -> int:
        """
        Calcula total de views ÚNICO por vídeo para um subniche no período

        IMPORTANTE: Remove duplicatas - cada vídeo conta apenas 1 vez (snapshot mais recente)
        """
        # Vídeos publicados nos últimos 30 dias
        cutoff_30d = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")

        response = self.db.table("videos_historico")\
            .select("video_id, views_atuais, data_coleta, canais_monitorados!inner(subnicho, tipo)")\
            .eq("canais_monitorados.subnicho", subniche)\
            .eq("canais_monitorados.tipo", "nosso")\
            .gte("data_publicacao", cutoff_30d)\
            .gte("data_coleta", date_start)\
            .lte("data_coleta", date_end)\
            .order("data_coleta", desc=True)\
            .execute()

        # Remove duplicatas: mantém apenas snapshot mais recente de cada vídeo
        videos_dict = {}
        for video in response.data:
            video_id = video['video_id']
            if video_id not in videos_dict:
                videos_dict[video_id] = video['views_atuais']

        total_views = sum(videos_dict.values())
        print(f"[ReportGenerator] {subniche}: {len(videos_dict)} vídeos únicos, {total_views:,} views totais no período")
        return total_views

    def _get_total_views_by_publication(self, subniche: str, days: int) -> Dict:
        """
        Calcula total de views de vídeos PUBLICADOS nos últimos X dias

        Args:
            subniche: Nome do subniche
            days: Janela de publicação (7 ou 30 dias)

        Returns:
            Dict com total_views e video_count
        """
        cutoff_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")

        # Buscar vídeos publicados nos últimos X dias
        response = self.db.table("videos_historico")\
            .select("video_id, views_atuais, data_coleta, canais_monitorados!inner(subnicho, tipo)")\
            .eq("canais_monitorados.subnicho", subniche)\
            .eq("canais_monitorados.tipo", "nosso")\
            .gte("data_publicacao", cutoff_date)\
            .order("data_coleta", desc=True)\
            .execute()

        # Remove duplicatas: mantém apenas snapshot mais recente de cada vídeo
        videos_dict = {}
        for video in response.data:
            video_id = video['video_id']
            if video_id not in videos_dict:
                videos_dict[video_id] = video['views_atuais']

        total_views = sum(videos_dict.values())
        video_count = len(videos_dict)

        print(f"[ReportGenerator] {subniche} ({days}d): {video_count} vídeos publicados, {total_views:,} views totais")
        return {
            'total_views': total_views,
            'video_count': video_count
        }

    def _generate_insight_for_subniche(self, subniche: str, growth_pct: float, views: int) -> str:
        """Gera insight automático baseado na performance"""
        if growth_pct > 10:
            return f"Excelente crescimento! {subniche} está performando acima da média. Continue investindo nesse tipo de conteúdo."
        elif growth_pct > 5:
            return f"Crescimento sólido. {subniche} está em boa trajetória. Mantenha a consistência de uploads."
        elif growth_pct > -5:
            return f"Estável. {subniche} mantém performance consistente. Considere testar novos formatos de título."
        else:
            return f"Atenção! {subniche} em queda. Revisar estratégia de conteúdo, thumbnails e títulos dos últimos vídeos."

    # =========================================================================
    # GAP ANALYSIS
    # =========================================================================

    def _get_gap_analysis(self) -> Dict:
        """
        Analisa gaps estratégicos em tempo real para cada subniche

        Returns:
            Dict com gaps por subniche
        """
        print("[ReportGenerator] Analisando gaps estratégicos...")

        # Buscar todos os subniches ativos
        subniches_response = self.db.table("canais_monitorados")\
            .select("subnicho")\
            .eq("tipo", "nosso")\
            .eq("status", "ativo")\
            .execute()

        subniches = list(set([c['subnicho'] for c in subniches_response.data]))

        # Analisar gaps para cada subniche
        gaps_by_subniche = {}
        total_gaps = 0

        for subniche in subniches:
            gaps_list = self.analyzer.analyze_gaps(subniche)

            if gaps_list:
                # Retornar formato NOVO (não converter!)
                gaps_by_subniche[subniche] = gaps_list
                total_gaps += len(gaps_list)

        print(f"[ReportGenerator] {total_gaps} gaps encontrados em {len(gaps_by_subniche)} subniches")
        return gaps_by_subniche

    def _get_top_10_keywords_by_subniche(self) -> Dict[str, List[Dict]]:
        """
        Gera top 10 keywords para cada subniche ativo (últimos 30 dias)

        Returns:
            Dict com keywords por subniche: {subniche: [keywords]}
        """
        print("[ReportGenerator] Gerando top 10 keywords por subniche...")

        # Buscar subniches ativos
        subniches_response = self.db.table("canais_monitorados")\
            .select("subnicho")\
            .eq("tipo", "nosso")\
            .eq("status", "ativo")\
            .execute()

        subniches = list(set([c['subnicho'] for c in subniches_response.data]))

        # Gerar keywords para cada subniche
        keywords_by_subniche = {}
        total_keywords = 0

        for subniche in subniches:
            # Usa analyzer.analyze_keywords() que JÁ filtra por subniche
            keywords = self.analyzer.analyze_keywords(subniche=subniche, period_days=30)

            if keywords:
                keywords_by_subniche[subniche] = keywords[:10]  # Top 10
                total_keywords += len(keywords[:10])

        print(f"[ReportGenerator] {total_keywords} keywords geradas para {len(keywords_by_subniche)} subniches")
        return keywords_by_subniche

    # =========================================================================
    # ANÁLISES AVANÇADAS (ALÉM DE TÍTULOS)
    # =========================================================================

    def _analyze_upload_frequency(self) -> Dict:
        """
        Analisa frequência de upload nossos canais vs concorrentes (últimos 30 dias)

        Returns:
            Dict com análise de frequência por subniche
        """
        print("[ReportGenerator] Analisando frequência de upload...")

        cutoff_date = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")

        # Buscar subniches
        response_subniches = self.db.table("canais_monitorados")\
            .select("subnicho")\
            .execute()

        subniches = list(set([item['subnicho'] for item in response_subniches.data]))

        frequency_analysis = {}

        for subniche in subniches:
            # Nossos canais
            response_nossos = self.db.table("videos_historico")\
                .select("canal_id, canais_monitorados!inner(nome_canal, tipo, subnicho)")\
                .eq("canais_monitorados.tipo", "nosso")\
                .eq("canais_monitorados.subnicho", subniche)\
                .gte("data_publicacao", cutoff_date)\
                .execute()

            nossos_videos = response_nossos.data
            nossos_canais = set([v['canal_id'] for v in nossos_videos])
            nossos_frequency = len(nossos_videos) / len(nossos_canais) if nossos_canais else 0

            # Concorrentes
            response_concorrentes = self.db.table("videos_historico")\
                .select("canal_id, canais_monitorados!inner(nome_canal, tipo, subnicho)")\
                .eq("canais_monitorados.tipo", "minerado")\
                .eq("canais_monitorados.subnicho", subniche)\
                .gte("data_publicacao", cutoff_date)\
                .execute()

            concorrentes_videos = response_concorrentes.data
            concorrentes_canais = set([v['canal_id'] for v in concorrentes_videos])
            concorrentes_frequency = len(concorrentes_videos) / len(concorrentes_canais) if concorrentes_canais else 0

            if nossos_frequency > 0 and concorrentes_frequency > 0:
                frequency_analysis[subniche] = {
                    'nossos_videos_per_canal': round(nossos_frequency, 1),
                    'concorrentes_videos_per_canal': round(concorrentes_frequency, 1),
                    'difference': round(concorrentes_frequency - nossos_frequency, 1)
                }

        print(f"[ReportGenerator] Análise de frequência concluída para {len(frequency_analysis)} subniches")
        return frequency_analysis

    def _analyze_engagement(self) -> Dict:
        """
        Analisa taxa de engajamento (likes/views) nossos vs concorrentes

        Returns:
            Dict com análise de engagement por subniche
        """
        print("[ReportGenerator] Analisando engagement...")

        cutoff_date = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")

        # Buscar subniches
        response_subniches = self.db.table("canais_monitorados")\
            .select("subnicho")\
            .execute()

        subniches = list(set([item['subnicho'] for item in response_subniches.data]))

        engagement_analysis = {}

        for subniche in subniches:
            # Nossos canais
            response_nossos = self.db.table("videos_historico")\
                .select("views_atuais, likes, canais_monitorados!inner(tipo, subnicho)")\
                .eq("canais_monitorados.tipo", "nosso")\
                .eq("canais_monitorados.subnicho", subniche)\
                .gte("data_publicacao", cutoff_date)\
                .gte("views_atuais", 1000)\
                .execute()

            nossos_videos = response_nossos.data

            # Concorrentes
            response_concorrentes = self.db.table("videos_historico")\
                .select("views_atuais, likes, canais_monitorados!inner(tipo, subnicho)")\
                .eq("canais_monitorados.tipo", "minerado")\
                .eq("canais_monitorados.subnicho", subniche)\
                .gte("data_publicacao", cutoff_date)\
                .gte("views_atuais", 1000)\
                .execute()

            concorrentes_videos = response_concorrentes.data

            if nossos_videos and concorrentes_videos:
                # Calcular taxa de engagement
                nossos_engagement = sum([
                    (v.get('likes', 0) / v['views_atuais'] * 100)
                    for v in nossos_videos if v['views_atuais'] > 0
                ]) / len(nossos_videos)

                concorrentes_engagement = sum([
                    (v.get('likes', 0) / v['views_atuais'] * 100)
                    for v in concorrentes_videos if v['views_atuais'] > 0
                ]) / len(concorrentes_videos)

                engagement_analysis[subniche] = {
                    'nossos_engagement_rate': round(nossos_engagement, 2),
                    'concorrentes_engagement_rate': round(concorrentes_engagement, 2),
                    'difference': round(concorrentes_engagement - nossos_engagement, 2)
                }

        print(f"[ReportGenerator] Análise de engagement concluída para {len(engagement_analysis)} subniches")
        return engagement_analysis

    def _analyze_video_duration(self) -> Dict:
        """
        Analisa duração média dos vídeos de sucesso (50k+ views)

        Returns:
            Dict com duração média por subniche
        """
        print("[ReportGenerator] Analisando duração de vídeos...")

        cutoff_date = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")

        # Buscar subniches
        response_subniches = self.db.table("canais_monitorados")\
            .select("subnicho")\
            .execute()

        subniches = list(set([item['subnicho'] for item in response_subniches.data]))

        duration_analysis = {}

        for subniche in subniches:
            # Vídeos de sucesso (50k+ views)
            response = self.db.table("videos_historico")\
                .select("duracao, views_atuais, canais_monitorados!inner(subnicho, tipo)")\
                .eq("canais_monitorados.subnicho", subniche)\
                .gte("data_publicacao", cutoff_date)\
                .gte("views_atuais", 50000)\
                .execute()

            videos = response.data

            if videos:
                # Calcular duração média
                durations = [v.get('duracao', 0) for v in videos if v.get('duracao', 0) > 0]

                if durations:
                    avg_duration = sum(durations) / len(durations)

                    duration_analysis[subniche] = {
                        'avg_duration_seconds': round(avg_duration, 0),
                        'avg_duration_minutes': round(avg_duration / 60, 1),
                        'video_count': len(durations)
                    }

        print(f"[ReportGenerator] Análise de duração concluída para {len(duration_analysis)} subniches")
        return duration_analysis

    # =========================================================================
    # AÇÕES RECOMENDADAS
    # =========================================================================

    def _generate_recommendations(self) -> Dict[str, Dict]:
        """
        Gera ações recomendadas AGRUPADAS POR SUBNICHE

        🆕 NOVA ESTRUTURA: 1 card por subniche com todas as recomendações

        Garante que TODOS os subniches nossos aparecem (mesmo que seja só "continuar assim")

        Returns:
            Dict com subniches como keys e recomendações agrupadas como values
            {
                'Contos Familiares': {
                    'status': 'growing',
                    'growth_percentage': 15.0,
                    'recommendations': [...]
                },
                ...
            }
        """
        print("[ReportGenerator] Gerando recomendações agrupadas por subniche...")

        # Estrutura: dict de subniches com suas recomendações
        recommendations_by_subniche = {}

        # Buscar dados de performance
        performance_data = self._get_performance_by_subniche(
            (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
        )

        # Inicializar dict com TODOS os subniches "nosso" e determinar status
        for perf in performance_data:
            subniche = perf['subniche']
            growth = perf['growth_percentage']

            # Determinar status
            if growth > 10:
                status = 'growing'
            elif growth < -10:
                status = 'declining'
            else:
                status = 'stable'

            recommendations_by_subniche[subniche] = {
                'status': status,
                'growth_percentage': growth,
                'recommendations': []
            }

        # Helper function para adicionar recomendação a um subniche
        def add_recommendation(subniche, recommendation):
            if subniche in recommendations_by_subniche:
                recommendations_by_subniche[subniche]['recommendations'].append(recommendation)

        # =====================================================================
        # 1. NOSSOS CANAIS - PROBLEMAS URGENTES (Subnichos em queda acentuada)
        # =====================================================================
        for perf in performance_data:
            if perf['growth_percentage'] < -10:  # Queda >10%
                add_recommendation(perf['subniche'], {
                    'priority': 'urgent',
                    'category': 'NOSSOS CANAIS - PROBLEMA',
                    'title': f"🔴 Queda acentuada de performance",
                    'description': f"Queda de {abs(perf['growth_percentage']):.1f}% nas views. Necessário ação imediata para reverter tendência negativa.",
                    'action': f"1) Revisar últimos 5 vídeos: thumbnails, títulos, hooks iniciais\n2) Comparar com concorrentes top deste subniche\n3) Testar novo formato de vídeo ou padrão de título\n4) Analisar retenção de audiência (primeiros 30s)",
                    'impact': 'CRÍTICO',
                    'effort': 'Alto'
                })

        # =====================================================================
        # 2. NOSSOS CANAIS - O QUE FAZEMOS BEM E DEVEMOS CONTINUAR
        # =====================================================================
        # Identifica top performers (subniches com crescimento >15%)
        top_performers = sorted(performance_data, key=lambda x: x['growth_percentage'], reverse=True)[:3]

        for perf in top_performers:
            if perf['growth_percentage'] > 15:
                # Busca vídeos TOP REAIS desse subniche (últimos 30 dias)
                cutoff_date = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")

                top_videos_response = self.db.table("videos_historico")\
                    .select("titulo, views_atuais, canais_monitorados!inner(tipo, subnicho)")\
                    .eq("canais_monitorados.tipo", "nosso")\
                    .eq("canais_monitorados.subnicho", perf['subniche'])\
                    .gte("data_publicacao", cutoff_date)\
                    .gte("views_atuais", 50000)\
                    .order("views_atuais", desc=True)\
                    .limit(3)\
                    .execute()

                if top_videos_response.data and len(top_videos_response.data) > 0:
                    top_video = top_videos_response.data[0]
                    avg_views = sum(v['views_atuais'] for v in top_videos_response.data) / len(top_videos_response.data)

                    add_recommendation(perf['subniche'], {
                        'priority': 'medium',
                        'category': 'NOSSOS CANAIS - CONTINUAR',
                        'title': f"✅ Performance excelente (+{perf['growth_percentage']:.1f}%)",
                        'description': f"Crescimento de {perf['growth_percentage']:.1f}% nas views. {len(top_videos_response.data)} vídeos com 50k+ views nos últimos 30 dias!",
                        'action': f"MANTER estratégia atual:\n• Continuar modelo que funciona (avg {avg_views:,.0f} views)\n• Top vídeo: \"{top_video['titulo']}\" ({top_video['views_atuais']:,} views)\n• Analisar esses {len(top_videos_response.data)} vídeos: o que têm em comum?\n• Replicar formato em outros subniches se possível",
                        'impact': 'MÉDIO',
                        'effort': 'Baixo',
                        'avg_views': int(avg_views)
                    })

        # =====================================================================
        # 3. NOSSOS CANAIS - O QUE FAZEMOS MAL E DEVEMOS MELHORAR
        # =====================================================================
        # Identifica underperformers (abaixo da média, mas não em queda crítica)
        if performance_data:
            avg_growth = sum(p['growth_percentage'] for p in performance_data) / len(performance_data)
            underperformers = [p for p in performance_data if p['growth_percentage'] < avg_growth * 0.5 and p['growth_percentage'] >= -10][:3]

            for perf in underperformers:
                add_recommendation(perf['subniche'], {
                    'priority': 'medium',
                    'category': 'NOSSOS CANAIS - MELHORAR',
                    'title': f"⚠️ Performance abaixo da média",
                    'description': f"Crescimento de apenas {perf['growth_percentage']:.1f}% vs média geral de {avg_growth:.1f}%. Há espaço para otimização.",
                    'action': f"1) Analisar top 3 vídeos dos concorrentes deste subniche\n2) Testar novos formatos de thumbnail (A/B test)\n3) Revisar SEO: título, descrição, tags\n4) Avaliar horário de postagem e frequência",
                    'impact': 'MÉDIO',
                    'effort': 'Médio'
                })

        # =====================================================================
        # 4. FREQUÊNCIA DE UPLOAD - Análise Comparativa
        # =====================================================================
        frequency_data = self._analyze_upload_frequency()

        for subniche, data in frequency_data.items():
            if data['difference'] > 3:  # Concorrentes postam 3+ vídeos a mais por canal
                add_recommendation(subniche, {
                    'priority': 'high',
                    'category': 'FREQUÊNCIA - AJUSTAR',
                    'title': f"📅 Frequência de upload baixa",
                    'description': f"Concorrentes postam {data['concorrentes_videos_per_canal']:.1f} vídeos/canal vs nossos {data['nossos_videos_per_canal']:.1f} (últimos 30 dias). Diferença de {data['difference']:.1f} vídeos/canal.",
                    'action': f"1) Aumentar produção para igualar concorrentes\n2) Se não conseguir produzir mais, priorizar qualidade sobre quantidade\n3) Considerar contratar editor adicional ou otimizar fluxo de produção\n4) Avaliar se falta de consistência afeta algoritmo do YouTube",
                    'impact': 'ALTO',
                    'effort': 'Alto'
                })
            elif data['difference'] < -3:  # Estamos postando muito mais
                add_recommendation(subniche, {
                    'priority': 'medium',
                    'category': 'FREQUÊNCIA - OTIMIZAR',
                    'title': f"📹 Excesso de uploads",
                    'description': f"Estamos postando {data['nossos_videos_per_canal']:.1f} vídeos/canal vs {data['concorrentes_videos_per_canal']:.1f} dos concorrentes (últimos 30 dias).",
                    'action': f"Avaliar se o excesso de uploads está afetando qualidade ou engagement. Considerar reduzir frequência e focar em vídeos com maior potencial de views.",
                    'impact': 'MÉDIO',
                    'effort': 'Baixo'
                })

        # =====================================================================
        # 5. ENGAGEMENT (LIKES/VIEWS) - Análise Comparativa
        # =====================================================================
        engagement_data = self._analyze_engagement()

        for subniche, data in engagement_data.items():
            if data['difference'] > 0.5:  # Concorrentes têm 0.5%+ engagement a mais
                add_recommendation(subniche, {
                    'priority': 'high',
                    'category': 'ENGAGEMENT - MELHORAR',
                    'title': f"👍 Baixo engagement",
                    'description': f"Taxa de likes nossos: {data['nossos_engagement_rate']:.2f}% vs concorrentes: {data['concorrentes_engagement_rate']:.2f}%. Diferença de {data['difference']:.2f}%.",
                    'action': f"1) Adicionar CTAs (Call To Action) mais fortes nos vídeos\n2) Pedir likes/comments de forma natural no início E fim do vídeo\n3) Criar momentos mais \"meme-áveis\" ou emocionais que incentivem reação\n4) Responder mais comentários para estimular comunidade\n5) Analisar thumbnails - podem não estar gerando expectativa suficiente",
                    'impact': 'ALTO',
                    'effort': 'Médio'
                })

        # =====================================================================
        # 6. DURAÇÃO DE VÍDEOS - Análise de Sucesso
        # =====================================================================
        duration_data = self._analyze_video_duration()

        for subniche, data in duration_data.items():
            if data['avg_duration_minutes'] > 0:
                add_recommendation(subniche, {
                    'priority': 'medium',
                    'category': 'DURAÇÃO - INSIGHT',
                    'title': f"⏱️ Duração ideal identificada",
                    'description': f"Vídeos de sucesso (50k+ views) têm média de {data['avg_duration_minutes']:.1f} minutos ({data['video_count']} vídeos analisados).",
                    'action': f"Usar {data['avg_duration_minutes']:.1f} minutos como referência para novos vídeos. Vídeos muito mais curtos ou longos podem performar pior.",
                    'impact': 'MÉDIO',
                    'effort': 'Baixo'
                })

        # =====================================================================
        # 7. GARANTIR QUE TODOS OS SUBNICHES TÊM PELO MENOS 1 RECOMENDAÇÃO
        # =====================================================================
        for subniche, data in recommendations_by_subniche.items():
            if len(data['recommendations']) == 0:
                # Adicionar recomendação padrão baseada no status
                if data['status'] == 'stable':
                    add_recommendation(subniche, {
                        'priority': 'low',
                        'category': 'NOSSOS CANAIS - MANTER',
                        'title': f"✅ Performance estável",
                        'description': f"Crescimento de {data['growth_percentage']:.1f}% nas views. Performance dentro do esperado.",
                        'action': f"Continuar estratégia atual. Monitorar concorrentes e testar pequenas otimizações quando possível (thumbnails, títulos, SEO).",
                        'impact': 'BAIXO',
                        'effort': 'Baixo'
                    })
                elif data['status'] == 'growing':
                    add_recommendation(subniche, {
                        'priority': 'low',
                        'category': 'NOSSOS CANAIS - MANTER',
                        'title': f"✅ Crescimento positivo",
                        'description': f"Crescimento de {data['growth_percentage']:.1f}% nas views. Subniche em boa trajetória.",
                        'action': f"Manter estratégia atual e identificar padrões de sucesso para replicar em outros subniches.",
                        'impact': 'BAIXO',
                        'effort': 'Baixo'
                    })

        # Ordenar recomendações dentro de cada subniche por prioridade
        priority_order = {'urgent': 0, 'high': 1, 'medium': 2, 'low': 3}
        for subniche in recommendations_by_subniche:
            recommendations_by_subniche[subniche]['recommendations'].sort(
                key=lambda x: priority_order.get(x['priority'], 4)
            )

        total_recommendations = sum(len(data['recommendations']) for data in recommendations_by_subniche.values())
        print(f"[ReportGenerator] {total_recommendations} recomendações agrupadas em {len(recommendations_by_subniche)} subniches")
        return recommendations_by_subniche

    # =========================================================================
    # SALVAR RELATÓRIO
    # =========================================================================

    def _save_report(self, report: Dict):
        """Salva relatório no banco de dados"""
        print("[ReportGenerator] Salvando relatório no banco...")

        try:
            self.db.table("weekly_reports").insert({
                'week_start': report['week_start'],
                'week_end': report['week_end'],
                'report_data': json.dumps(report)
            }).execute()

            print("[ReportGenerator] Relatório salvo com sucesso!")

        except Exception as e:
            print(f"[ReportGenerator] Erro ao salvar relatório: {e}")

    # =========================================================================
    # BUSCAR ÚLTIMO RELATÓRIO
    # =========================================================================

    def get_latest_report(self) -> Dict:
        """
        Busca o relatório mais recente

        Returns:
            Dict com dados do último relatório
        """
        print("[ReportGenerator] Buscando último relatório...")

        response = self.db.table("weekly_reports")\
            .select("*")\
            .order("week_start", desc=True)\
            .limit(1)\
            .execute()

        if response.data:
            report_data = response.data[0]
            return json.loads(report_data['report_data'])

        print("[ReportGenerator] Nenhum relatório encontrado")
        return None
