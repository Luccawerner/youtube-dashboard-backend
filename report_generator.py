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


class ReportGenerator:
    """Gerador de relatórios semanais"""

    def __init__(self, db_client):
        """
        Inicializa o gerador

        Args:
            db_client: Cliente Supabase para acesso ao banco
        """
        self.db = db_client

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
            'performance_by_subniche': self._get_performance_by_subniche(week_start),
            'gap_analysis': self._get_gap_analysis(),
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
        Busca top 10 vídeos por tipo de canal (nossos ou minerados)

        Args:
            tipo_canal: 'nosso' ou 'minerado'
            week_start: Data início da semana
            week_end: Data fim da semana

        Returns:
            Lista com top 10 vídeos ordenados por views dos últimos 7 dias
        """
        print(f"[ReportGenerator] Buscando top 10 vídeos ({tipo_canal})...")

        # Buscar vídeos postados nos últimos 30 dias
        cutoff_date_30d = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")

        # Query: vídeos postados nos últimos 30 dias, ordenados por views dos últimos 7 dias
        response = self.db.table("videos_historico")\
            .select("*, canais_monitorados!inner(nome_canal, tipo, id)")\
            .eq("canais_monitorados.tipo", tipo_canal)\
            .gte("data_publicacao", cutoff_date_30d)\
            .gte("data_coleta", week_start)\
            .lte("data_coleta", week_end)\
            .order("views_atuais", desc=True)\
            .limit(10)\
            .execute()

        videos = response.data

        # Calcular inscritos ganhos para cada canal nos últimos 7 dias
        result = []
        for video in videos:
            canal_id = video['canais_monitorados']['id']

            # Buscar dados do canal nos últimos 7 dias
            subs_gained = self._get_subscribers_gained(canal_id, 7)

            result.append({
                'video_id': video['video_id'],
                'titulo': video['titulo'],
                'canal_nome': video['canais_monitorados']['nome_canal'],
                'views_7d': video['views_atuais'],
                'subscribers_gained_7d': subs_gained,
                'url_video': video.get('url_video', '')
            })

        print(f"[ReportGenerator] {len(result)} vídeos encontrados ({tipo_canal})")
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

            result.append({
                'subniche': subniche,
                'views_current_week': views_current,
                'views_previous_week': views_previous,
                'growth_percentage': round(growth_pct, 1),
                'insight': insight
            })

        print(f"[ReportGenerator] {len(result)} subniches analisados")
        return result

    def _get_total_views_for_subniche(self, subniche: str, date_start: str, date_end: str) -> int:
        """Calcula total de views para um subniche no período"""
        # Baseado nos últimos 30 dias de coleta, filtrar apenas views do período
        cutoff_30d = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")

        response = self.db.table("videos_historico")\
            .select("views_atuais, canais_monitorados!inner(subnicho, tipo)")\
            .eq("canais_monitorados.subnicho", subniche)\
            .eq("canais_monitorados.tipo", "nosso")\
            .gte("data_coleta", cutoff_30d)\
            .gte("data_coleta", date_start)\
            .lte("data_coleta", date_end)\
            .execute()

        total_views = sum([v['views_atuais'] for v in response.data])
        return total_views

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
        Busca análise de gaps mais recente por subniche

        Returns:
            Dict com gaps por subniche
        """
        print("[ReportGenerator] Buscando gap analysis...")

        # Buscar gaps da semana atual
        week_start = (datetime.now() - timedelta(days=datetime.now().weekday())).strftime("%Y-%m-%d")

        response = self.db.table("gap_analysis")\
            .select("*")\
            .eq("analyzed_week_start", week_start)\
            .order("avg_views", desc=True)\
            .execute()

        gaps = response.data

        # Agrupar por subniche
        gaps_by_subniche = {}
        for gap in gaps:
            subniche = gap['subniche']

            if subniche not in gaps_by_subniche:
                gaps_by_subniche[subniche] = []

            gaps_by_subniche[subniche].append({
                'gap_title': gap['gap_title'],
                'description': gap['gap_description'],
                'competitor_count': gap['competitor_count'],
                'avg_views': gap['avg_views'],
                'recommendation': gap['recommendation']
            })

        print(f"[ReportGenerator] {len(gaps)} gaps encontrados")
        return gaps_by_subniche

    # =========================================================================
    # AÇÕES RECOMENDADAS
    # =========================================================================

    def _generate_recommendations(self) -> List[Dict]:
        """
        Gera lista de ações recomendadas ESTRATÉGICAS com 4 tipos de insights:
        1. NOSSOS CANAIS - PROBLEMAS (urgente)
        2. CONCORRENTES - COPIAR (alta prioridade)
        3. NOSSOS CANAIS - CONTINUAR (média prioridade)
        4. NOSSOS CANAIS - MELHORAR (média prioridade)

        Returns:
            Lista de recomendações priorizadas com category, impact, effort, avg_views
        """
        print("[ReportGenerator] Gerando recomendações estratégicas...")

        recommendations = []

        # Buscar dados de performance
        performance_data = self._get_performance_by_subniche(
            (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
        )

        # =====================================================================
        # 1. NOSSOS CANAIS - PROBLEMAS URGENTES (Subnichos em queda acentuada)
        # =====================================================================
        for perf in performance_data:
            if perf['growth_percentage'] < -10:  # Queda >10%
                recommendations.append({
                    'priority': 'urgent',
                    'category': 'NOSSOS CANAIS - PROBLEMA',
                    'title': f"🔴 {perf['subniche']} em queda acentuada",
                    'description': f"Queda de {abs(perf['growth_percentage']):.1f}% nas views. Necessário ação imediata para reverter tendência negativa.",
                    'action': f"1) Revisar últimos 5 vídeos: thumbnails, títulos, hooks iniciais\n2) Comparar com concorrentes top do subniche {perf['subniche']}\n3) Testar novo formato de vídeo ou padrão de título\n4) Analisar retenção de audiência (primeiros 30s)",
                    'impact': 'CRÍTICO',
                    'effort': 'Alto'
                })

        # =====================================================================
        # 2. CONCORRENTES - O QUE ELES FAZEM BEM E DEVEMOS COPIAR
        # =====================================================================
        gaps = self._get_gap_analysis()
        gap_count = 0
        for subniche, gap_list in list(gaps.items())[:3]:  # Top 3 subniches com gaps
            if gap_list and gap_count < 3:
                top_gap = gap_list[0]
                recommendations.append({
                    'priority': 'high',
                    'category': 'CONCORRENTES - COPIAR',
                    'title': f"🎯 Oportunidade em {subniche}",
                    'description': f"{top_gap['gap_title']}: {top_gap['competitor_count']} concorrentes fazem isso e nós não. Média de {top_gap['avg_views']:,} views.",
                    'action': top_gap['recommendation'],
                    'impact': 'ALTO',
                    'effort': 'Médio',
                    'avg_views': top_gap['avg_views']
                })
                gap_count += 1

        # =====================================================================
        # 3. NOSSOS CANAIS - O QUE FAZEMOS BEM E DEVEMOS CONTINUAR
        # =====================================================================
        # Identifica top performers (subniches com crescimento >15%)
        top_performers = sorted(performance_data, key=lambda x: x['growth_percentage'], reverse=True)[:2]

        for perf in top_performers:
            if perf['growth_percentage'] > 15:
                # Busca padrão de sucesso desse subniche
                patterns_response = self.db.table("title_patterns")\
                    .select("*")\
                    .eq("subniche", perf['subniche'])\
                    .eq("analyzed_date", datetime.now().strftime("%Y-%m-%d"))\
                    .order("avg_views", desc=True)\
                    .limit(1)\
                    .execute()

                if patterns_response.data:
                    pattern = patterns_response.data[0]
                    recommendations.append({
                        'priority': 'medium',
                        'category': 'NOSSOS CANAIS - CONTINUAR',
                        'title': f"✅ {perf['subniche']} performando excelente (+{perf['growth_percentage']:.1f}%)",
                        'description': f"Crescimento de {perf['growth_percentage']:.1f}% nas views. Fórmula está funcionando muito bem!",
                        'action': f"MANTER estratégia atual:\n• Continuar usando padrão: {pattern['pattern_structure']}\n• Exemplo de sucesso: \"{pattern['example_title']}\"\n• Replicar em outros subniches se possível",
                        'impact': 'MÉDIO',
                        'effort': 'Baixo',
                        'avg_views': pattern['avg_views']
                    })

        # =====================================================================
        # 4. NOSSOS CANAIS - O QUE FAZEMOS MAL E DEVEMOS MELHORAR
        # =====================================================================
        # Identifica underperformers (abaixo da média)
        if performance_data:
            avg_growth = sum(p['growth_percentage'] for p in performance_data) / len(performance_data)
            underperformers = [p for p in performance_data if p['growth_percentage'] < avg_growth * 0.5][:2]

            for perf in underperformers:
                recommendations.append({
                    'priority': 'medium',
                    'category': 'NOSSOS CANAIS - MELHORAR',
                    'title': f"⚠️ {perf['subniche']} abaixo da média",
                    'description': f"Crescimento de apenas {perf['growth_percentage']:.1f}% vs média geral de {avg_growth:.1f}%. Há espaço para otimização.",
                    'action': f"1) Analisar top 3 vídeos dos concorrentes de {perf['subniche']}\n2) Testar novos formatos de thumbnail (A/B test)\n3) Revisar SEO: título, descrição, tags\n4) Avaliar horário de postagem e frequência",
                    'impact': 'MÉDIO',
                    'effort': 'Médio'
                })

        # =====================================================================
        # 5. OPORTUNIDADES - KEYWORDS TRENDING
        # =====================================================================
        # Busca keywords que estão ganhando tração (últimos 7 dias)
        keywords_response = self.db.table("keyword_analysis")\
            .select("*")\
            .eq("period_days", 7)\
            .eq("analyzed_date", datetime.now().strftime("%Y-%m-%d"))\
            .order("frequency", desc=True)\
            .limit(3)\
            .execute()

        if keywords_response.data:
            trending_keywords = [k['keyword'] for k in keywords_response.data[:3]]
            recommendations.append({
                'priority': 'medium',
                'category': 'OPORTUNIDADE - TRENDING',
                'title': f"📈 Keywords em alta nos últimos 7 dias",
                'description': f"Palavras-chave ganhando tração: {', '.join(trending_keywords)}",
                'action': f"Criar vídeos priorizando essas keywords nos títulos, descrições e tags. Aproveitar a onda de interesse!",
                'impact': 'MÉDIO',
                'effort': 'Baixo'
            })

        # Ordenar por prioridade
        priority_order = {'urgent': 0, 'high': 1, 'medium': 2}
        recommendations.sort(key=lambda x: priority_order.get(x['priority'], 3))

        print(f"[ReportGenerator] {len(recommendations)} recomendações estratégicas geradas")
        return recommendations[:8]  # Top 8 recomendações mais importantes

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
