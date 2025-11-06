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
            .select("*, canais_monitorados!inner(nome_canal, tipo, id)")\
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
                'views_atuais': video['views_atuais'],
                'likes_atuais': video.get('likes_atuais', 0),
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
            .select("DISTINCT subnicho")\
            .execute()

        subniches = [item['subnicho'] for item in response_subniches.data]

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
            .select("DISTINCT subnicho")\
            .execute()

        subniches = [item['subnicho'] for item in response_subniches.data]

        engagement_analysis = {}

        for subniche in subniches:
            # Nossos canais
            response_nossos = self.db.table("videos_historico")\
                .select("views_atuais, likes_atuais, canais_monitorados!inner(tipo, subnicho)")\
                .eq("canais_monitorados.tipo", "nosso")\
                .eq("canais_monitorados.subnicho", subniche)\
                .gte("data_publicacao", cutoff_date)\
                .gte("views_atuais", 1000)\
                .execute()

            nossos_videos = response_nossos.data

            # Concorrentes
            response_concorrentes = self.db.table("videos_historico")\
                .select("views_atuais, likes_atuais, canais_monitorados!inner(tipo, subnicho)")\
                .eq("canais_monitorados.tipo", "minerado")\
                .eq("canais_monitorados.subnicho", subniche)\
                .gte("data_publicacao", cutoff_date)\
                .gte("views_atuais", 1000)\
                .execute()

            concorrentes_videos = response_concorrentes.data

            if nossos_videos and concorrentes_videos:
                # Calcular taxa de engagement
                nossos_engagement = sum([
                    (v.get('likes_atuais', 0) / v['views_atuais'] * 100)
                    for v in nossos_videos if v['views_atuais'] > 0
                ]) / len(nossos_videos)

                concorrentes_engagement = sum([
                    (v.get('likes_atuais', 0) / v['views_atuais'] * 100)
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
            .select("DISTINCT subnicho")\
            .execute()

        subniches = [item['subnicho'] for item in response_subniches.data]

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

                # Estrutura NOVA dos gaps
                gap_type_translate = {
                    'duration': 'Duração de vídeos',
                    'frequency': 'Frequência de postagem',
                    'engagement': 'Engajamento'
                }
                gap_type = gap_type_translate.get(top_gap['type'], top_gap['type'])

                recommendations.append({
                    'priority': 'high',
                    'category': 'CONCORRENTES - COPIAR',
                    'title': f"🎯 {gap_type} em {subniche}",
                    'description': f"{top_gap['title']}: Você está em {top_gap['your_value']}, concorrentes em {top_gap['competitor_value']}. {top_gap['impact_description']}",
                    'action': '\n'.join([f"• {action}" for action in top_gap['actions']]),
                    'impact': top_gap['priority_text'],
                    'effort': top_gap['effort']
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

        # =====================================================================
        # 6. FREQUÊNCIA DE UPLOAD - Análise Comparativa
        # =====================================================================
        frequency_data = self._analyze_upload_frequency()

        for subniche, data in list(frequency_data.items())[:2]:
            if data['difference'] > 3:  # Concorrentes postam 3+ vídeos a mais por canal
                recommendations.append({
                    'priority': 'high',
                    'category': 'FREQUÊNCIA - AJUSTAR',
                    'title': f"📅 Frequência de upload baixa em {subniche}",
                    'description': f"Concorrentes postam {data['concorrentes_videos_per_canal']:.1f} vídeos/canal vs nossos {data['nossos_videos_per_canal']:.1f} (últimos 30 dias). Diferença de {data['difference']:.1f} vídeos/canal.",
                    'action': f"1) Aumentar produção de {subniche} para igualar concorrentes\n2) Se não conseguir produzir mais, priorizar qualidade sobre quantidade\n3) Considerar contratar editor adicional ou otimizar fluxo de produção\n4) Avaliar se falta de consistência afeta algoritmo do YouTube",
                    'impact': 'ALTO',
                    'effort': 'Alto'
                })
            elif data['difference'] < -3:  # Estamos postando muito mais
                recommendations.append({
                    'priority': 'medium',
                    'category': 'FREQUÊNCIA - OTIMIZAR',
                    'title': f"📹 Excesso de uploads em {subniche}",
                    'description': f"Estamos postando {data['nossos_videos_per_canal']:.1f} vídeos/canal vs {data['concorrentes_videos_per_canal']:.1f} dos concorrentes (últimos 30 dias).",
                    'action': f"Avaliar se o excesso de uploads está afetando qualidade ou engagement. Considerar reduzir frequência e focar em vídeos com maior potencial de views.",
                    'impact': 'MÉDIO',
                    'effort': 'Baixo'
                })

        # =====================================================================
        # 7. ENGAGEMENT (LIKES/VIEWS) - Análise Comparativa
        # =====================================================================
        engagement_data = self._analyze_engagement()

        for subniche, data in list(engagement_data.items())[:2]:
            if data['difference'] > 0.5:  # Concorrentes têm 0.5%+ engagement a mais
                recommendations.append({
                    'priority': 'high',
                    'category': 'ENGAGEMENT - MELHORAR',
                    'title': f"👍 Baixo engagement em {subniche}",
                    'description': f"Taxa de likes nossos: {data['nossos_engagement_rate']:.2f}% vs concorrentes: {data['concorrentes_engagement_rate']:.2f}%. Diferença de {data['difference']:.2f}%.",
                    'action': f"1) Adicionar CTAs (Call To Action) mais fortes nos vídeos de {subniche}\n2) Pedir likes/comments de forma natural no início E fim do vídeo\n3) Criar momentos mais \"meme-áveis\" ou emocionais que incentivem reação\n4) Responder mais comentários para estimular comunidade\n5) Analisar thumbnails - podem não estar gerando expectativa suficiente",
                    'impact': 'ALTO',
                    'effort': 'Médio'
                })

        # =====================================================================
        # 8. DURAÇÃO DE VÍDEOS - Análise de Sucesso
        # =====================================================================
        duration_data = self._analyze_video_duration()

        for subniche, data in list(duration_data.items())[:2]:
            if data['avg_duration_minutes'] > 0:
                recommendations.append({
                    'priority': 'medium',
                    'category': 'DURAÇÃO - INSIGHT',
                    'title': f"⏱️ Duração ideal para {subniche}",
                    'description': f"Vídeos de sucesso (50k+ views) em {subniche} têm média de {data['avg_duration_minutes']:.1f} minutos ({data['video_count']} vídeos analisados).",
                    'action': f"Usar {data['avg_duration_minutes']:.1f} minutos como referência para novos vídeos de {subniche}. Vídeos muito mais curtos ou longos podem performar pior.",
                    'impact': 'MÉDIO',
                    'effort': 'Baixo'
                })

        # Ordenar por prioridade
        priority_order = {'urgent': 0, 'high': 1, 'medium': 2}
        recommendations.sort(key=lambda x: priority_order.get(x['priority'], 3))

        print(f"[ReportGenerator] {len(recommendations)} recomendações estratégicas geradas")
        return recommendations[:12]  # Top 12 recomendações mais importantes

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
