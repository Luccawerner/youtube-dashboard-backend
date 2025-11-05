"""
analyzer.py - Lógica de análise para Analysis Tab
Author: Claude Code
Date: 2024-11-05

Funções:
- analyze_keywords(): Extrai top 20 keywords dos títulos
- analyze_title_patterns(): Detecta padrões de título vencedores
- analyze_top_channels(): Identifica top 5 canais por subniche
- analyze_gaps(): Compara o que concorrentes fazem vs nossos canais
"""

import re
from collections import Counter
from datetime import datetime, timedelta
from typing import List, Dict, Tuple
import json

# Stop words em inglês (palavras comuns que não são keywords relevantes)
STOP_WORDS = {
    'a', 'an', 'and', 'are', 'as', 'at', 'be', 'by', 'for', 'from', 'has', 'he',
    'in', 'is', 'it', 'its', 'of', 'on', 'that', 'the', 'to', 'was', 'will', 'with',
    'music', 'video', 'channel', 'new', 'best', 'top', 'hour', 'hours', 'minute', 'minutes',
    'full', 'hd', 'hq', '1080p', '720p', '4k', '2024', '2023', '2022'
}


class Analyzer:
    """Classe principal para análises do dashboard"""

    def __init__(self, db_client):
        """
        Inicializa o analisador

        Args:
            db_client: Cliente Supabase para acesso ao banco
        """
        self.db = db_client

    # =========================================================================
    # ANÁLISE DE KEYWORDS
    # =========================================================================

    def analyze_keywords(self, period_days: int = 30) -> List[Dict]:
        """
        Analisa keywords mais frequentes nos títulos dos vídeos

        Args:
            period_days: Período em dias (7, 15 ou 30)

        Returns:
            Lista com top 20 keywords ordenadas por frequência × performance
        """
        print(f"[Analyzer] Analisando keywords (últimos {period_days} dias)...")

        # Buscar vídeos do período
        cutoff_date = datetime.now() - timedelta(days=period_days)

        response = self.db.table("videos_historico")\
            .select("titulo, views_atuais, data_coleta")\
            .gte("data_coleta", cutoff_date.strftime("%Y-%m-%d"))\
            .execute()

        videos = response.data

        if not videos:
            print("[Analyzer] Nenhum vídeo encontrado no período")
            return []

        # Extrair keywords de todos os títulos
        keyword_stats = {}  # {keyword: {'count': int, 'total_views': int, 'video_ids': set}}

        for video in videos:
            titulo = video.get('titulo', '').lower()
            views = video.get('views_atuais', 0)

            # Extrair palavras (remover números, pontuação)
            words = re.findall(r'\b[a-z]{3,}\b', titulo)

            for word in words:
                # Pular stop words
                if word in STOP_WORDS:
                    continue

                if word not in keyword_stats:
                    keyword_stats[word] = {
                        'count': 0,
                        'total_views': 0,
                        'videos': set()
                    }

                keyword_stats[word]['count'] += 1
                keyword_stats[word]['total_views'] += views
                keyword_stats[word]['videos'].add(video.get('video_id', ''))

        # Calcular score e ordenar
        keyword_list = []
        for keyword, stats in keyword_stats.items():
            avg_views = stats['total_views'] // stats['count'] if stats['count'] > 0 else 0
            video_count = len(stats['videos'])

            # Score: frequência × log(views médias) - favorece keywords com boa performance
            score = stats['count'] * (avg_views ** 0.5)

            keyword_list.append({
                'keyword': keyword,
                'frequency': stats['count'],
                'avg_views': avg_views,
                'video_count': video_count,
                'score': score
            })

        # Ordenar por score e pegar top 20
        keyword_list.sort(key=lambda x: x['score'], reverse=True)
        top_20 = keyword_list[:20]

        print(f"[Analyzer] {len(top_20)} keywords analisadas")
        return top_20

    # =========================================================================
    # ANÁLISE DE PADRÕES DE TÍTULO
    # =========================================================================

    def analyze_title_patterns(self, subniche: str, period_days: int = 30) -> List[Dict]:
        """
        Detecta padrões de título vencedores por subniche

        Args:
            subniche: Subniche a analisar
            period_days: Período em dias (7, 15 ou 30)

        Returns:
            Lista com top 5 padrões de título ordenados por performance
        """
        print(f"[Analyzer] Analisando padrões de título ({subniche}, {period_days} dias)...")

        # Buscar vídeos do período e subniche
        cutoff_date = datetime.now() - timedelta(days=period_days)

        response = self.db.table("videos_historico")\
            .select("videos_historico.*, canais_monitorados!inner(subnicho)")\
            .eq("canais_monitorados.subnicho", subniche)\
            .gte("data_coleta", cutoff_date.strftime("%Y-%m-%d"))\
            .execute()

        videos = response.data

        if not videos:
            print(f"[Analyzer] Nenhum vídeo encontrado para {subniche}")
            return []

        # Detectar padrões
        patterns = {}  # {pattern_key: {'structure': str, 'examples': [], 'views': [], 'count': int}}

        for video in videos:
            titulo = video.get('titulo', '')
            views = video.get('views_atuais', 0)

            # Detectar padrão do título
            pattern = self._detect_title_pattern(titulo)

            if pattern not in patterns:
                patterns[pattern] = {
                    'structure': pattern,
                    'examples': [],
                    'views': [],
                    'count': 0
                }

            patterns[pattern]['examples'].append(titulo)
            patterns[pattern]['views'].append(views)
            patterns[pattern]['count'] += 1

        # Calcular performance e ordenar
        pattern_list = []
        for pattern_key, data in patterns.items():
            if data['count'] < 3:  # Mínimo de 3 vídeos para ser considerado padrão
                continue

            avg_views = sum(data['views']) // len(data['views'])

            # Pegar melhor exemplo (maior views)
            best_example_idx = data['views'].index(max(data['views']))
            best_example = data['examples'][best_example_idx]

            pattern_list.append({
                'pattern_structure': pattern_key,
                'pattern_description': self._describe_pattern(pattern_key),
                'example_title': best_example,
                'avg_views': avg_views,
                'video_count': data['count']
            })

        # Ordenar por views médias e pegar top 5
        pattern_list.sort(key=lambda x: x['avg_views'], reverse=True)
        top_5 = pattern_list[:5]

        print(f"[Analyzer] {len(top_5)} padrões identificados para {subniche}")
        return top_5

    def _detect_title_pattern(self, titulo: str) -> str:
        """Detecta o padrão estrutural de um título"""

        # Padrões comuns (ordenados por prioridade)
        patterns = [
            # [Número] Hours/Minutes + [Descrição]
            (r'^\d+\s+(hours?|minutes?|mins?|hrs?)\s+', '[Número] [Tempo] + [Descrição]'),

            # [Hora específica] + [Música] + to [Ação]
            (r'^\d+[ap]m\s+', '[Hora] + [Música] + [Ação]'),

            # [Adjetivo] + [Tipo] + for [Contexto]
            (r'\b(cozy|chill|relaxing|smooth|soft|calm|peaceful)\b.*\bfor\b', '[Adjetivo] + [Tipo] + for [Contexto]'),

            # [Tipo de música] + [Instrumento]
            (r'\b(jazz|lofi|blues|rock)\b.*\b(piano|guitar|saxophone|violin)\b', '[Tipo] + [Instrumento]'),

            # [Clima/Ambiente] + [Música] + [Benefício]
            (r'\b(rainy|snowy|winter|summer|night|morning)\b', '[Ambiente] + [Música] + [Benefício]'),

            # [Música] + to/for [Ação] + and [Ação]
            (r'\b(to|for)\b.*\band\b', '[Música] + [Ação] and [Ação]'),

            # [Frequência] Hz + [Descrição]
            (r'\b\d+hz\b', '[Frequência Hz] + [Descrição]'),
        ]

        titulo_lower = titulo.lower()

        for pattern_regex, pattern_name in patterns:
            if re.search(pattern_regex, titulo_lower):
                return pattern_name

        # Padrão genérico
        return '[Título Padrão]'

    def _describe_pattern(self, pattern_structure: str) -> str:
        """Gera descrição legível do padrão"""
        descriptions = {
            '[Número] [Tempo] + [Descrição]': 'Duração específica + descrição do conteúdo',
            '[Hora] + [Música] + [Ação]': 'Horário específico + gênero + propósito',
            '[Adjetivo] + [Tipo] + for [Contexto]': 'Qualificador emocional + gênero + uso',
            '[Tipo] + [Instrumento]': 'Gênero musical + instrumento específico',
            '[Ambiente] + [Música] + [Benefício]': 'Contexto ambiental + gênero + efeito',
            '[Música] + [Ação] and [Ação]': 'Gênero + dupla finalidade',
            '[Frequência Hz] + [Descrição]': 'Frequência específica + benefício',
            '[Título Padrão]': 'Estrutura não categorizada'
        }
        return descriptions.get(pattern_structure, 'Padrão genérico')

    # =========================================================================
    # ANÁLISE DE TOP CHANNELS
    # =========================================================================

    def analyze_top_channels(self, subniche: str) -> List[Dict]:
        """
        Identifica top 5 canais por subniche (últimos 30 dias)

        Args:
            subniche: Subniche a analisar

        Returns:
            Lista com top 5 canais ordenados por views_30d
        """
        print(f"[Analyzer] Analisando top channels ({subniche})...")

        # Buscar canais minerados do subniche
        cutoff_date = datetime.now() - timedelta(days=30)

        response = self.db.table("dados_canais_historico")\
            .select("*, canais_monitorados!inner(id, nome_canal, url_canal, subnicho, tipo)")\
            .eq("canais_monitorados.subnicho", subniche)\
            .eq("canais_monitorados.tipo", "minerado")\
            .gte("data_coleta", cutoff_date.strftime("%Y-%m-%d"))\
            .order("data_coleta", desc=True)\
            .execute()

        channels_data = response.data

        if not channels_data:
            print(f"[Analyzer] Nenhum canal encontrado para {subniche}")
            return []

        # Agrupar por canal e pegar dados mais recentes
        channels_by_id = {}
        for row in channels_data:
            canal_id = row['canal_id']

            if canal_id not in channels_by_id:
                channels_by_id[canal_id] = {
                    'canal_id': canal_id,
                    'nome_canal': row['canais_monitorados']['nome_canal'],
                    'url_canal': row['canais_monitorados']['url_canal'],
                    'views_30d': row['views_30d'],
                    'inscritos': row['inscritos'],
                    'data_coleta': row['data_coleta']
                }

        # Calcular inscritos ganhos (comparar snapshots de 30 dias atrás)
        for canal_id, data in channels_by_id.items():
            # Buscar snapshot de 30 dias atrás
            old_date = datetime.now() - timedelta(days=60)

            old_response = self.db.table("dados_canais_historico")\
                .select("inscritos")\
                .eq("canal_id", canal_id)\
                .lte("data_coleta", old_date.strftime("%Y-%m-%d"))\
                .order("data_coleta", desc=True)\
                .limit(1)\
                .execute()

            old_subs = old_response.data[0]['inscritos'] if old_response.data else data['inscritos']
            data['subscribers_gained_30d'] = data['inscritos'] - old_subs

        # Ordenar por views_30d e pegar top 5
        channel_list = list(channels_by_id.values())
        channel_list.sort(key=lambda x: x['views_30d'], reverse=True)
        top_5 = channel_list[:5]

        print(f"[Analyzer] {len(top_5)} canais identificados para {subniche}")
        return top_5

    # =========================================================================
    # GAP ANALYSIS
    # =========================================================================

    def analyze_gaps(self, subniche: str) -> List[Dict]:
        """
        Identifica gaps (o que concorrentes fazem que nós não fazemos)

        Args:
            subniche: Subniche a analisar

        Returns:
            Lista de oportunidades/gaps identificados
        """
        print(f"[Analyzer] Analisando gaps ({subniche})...")

        # Buscar padrões dos canais minerados
        minerados_patterns = self.analyze_title_patterns(subniche, period_days=30)

        # Buscar padrões dos nossos canais
        # (Para isso, precisamos modificar a query para buscar tipo='nosso')
        response = self.db.table("videos_historico")\
            .select("videos_historico.*, canais_monitorados!inner(subnicho, tipo)")\
            .eq("canais_monitorados.subnicho", subniche)\
            .eq("canais_monitorados.tipo", "nosso")\
            .gte("data_coleta", (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d"))\
            .execute()

        nossos_videos = response.data

        # Detectar padrões dos nossos vídeos
        nossos_patterns = set()
        for video in nossos_videos:
            titulo = video.get('titulo', '')
            pattern = self._detect_title_pattern(titulo)
            nossos_patterns.add(pattern)

        # Identificar gaps (padrões que minerados usam mas nós não)
        gaps = []
        for pattern in minerados_patterns:
            pattern_key = pattern['pattern_structure']

            if pattern_key not in nossos_patterns:
                # Gap identificado!
                gaps.append({
                    'gap_title': f"Padrão não utilizado: {pattern_key}",
                    'gap_description': pattern['pattern_description'],
                    'competitor_count': pattern['video_count'],
                    'avg_views': pattern['avg_views'],
                    'example_videos': [pattern['example_title']],
                    'recommendation': f"Considere produzir vídeos usando a estrutura: {pattern_key}"
                })

        print(f"[Analyzer] {len(gaps)} gaps identificados para {subniche}")
        return gaps[:5]  # Top 5 gaps


# =========================================================================
# FUNÇÕES AUXILIARES
# =========================================================================

def save_analysis_to_db(db_client, analysis_type: str, data: List[Dict], period_days: int = None, subniche: str = None):
    """
    Salva resultados da análise no banco

    Args:
        db_client: Cliente Supabase
        analysis_type: Tipo de análise ('keywords', 'patterns', 'channels', 'gaps')
        data: Dados a salvar
        period_days: Período analisado (para keywords/patterns)
        subniche: Subniche analisado (para patterns/channels/gaps)
    """
    today = datetime.now().strftime("%Y-%m-%d")

    if analysis_type == 'keywords':
        # Salvar em keyword_analysis
        for item in data:
            db_client.table("keyword_analysis").upsert({
                'keyword': item['keyword'],
                'period_days': period_days,
                'frequency': item['frequency'],
                'avg_views': item['avg_views'],
                'video_count': item['video_count'],
                'analyzed_date': today
            }, on_conflict='keyword,period_days,analyzed_date').execute()

    elif analysis_type == 'patterns':
        # Salvar em title_patterns
        for item in data:
            db_client.table("title_patterns").upsert({
                'subniche': subniche,
                'period_days': period_days,
                'pattern_structure': item['pattern_structure'],
                'pattern_description': item['pattern_description'],
                'example_title': item['example_title'],
                'avg_views': item['avg_views'],
                'video_count': item['video_count'],
                'analyzed_date': today
            }, on_conflict='subniche,pattern_structure,period_days,analyzed_date').execute()

    elif analysis_type == 'channels':
        # Salvar em top_channels_snapshot
        for rank, item in enumerate(data, 1):
            db_client.table("top_channels_snapshot").upsert({
                'canal_id': item['canal_id'],
                'subniche': subniche,
                'views_30d': item['views_30d'],
                'subscribers_gained_30d': item['subscribers_gained_30d'],
                'rank_position': rank,
                'snapshot_date': today
            }, on_conflict='canal_id,subniche,snapshot_date').execute()

    elif analysis_type == 'gaps':
        # Salvar em gap_analysis
        week_start = (datetime.now() - timedelta(days=datetime.now().weekday())).strftime("%Y-%m-%d")
        week_end = (datetime.now() + timedelta(days=6-datetime.now().weekday())).strftime("%Y-%m-%d")

        for item in data:
            db_client.table("gap_analysis").upsert({
                'subniche': subniche,
                'gap_title': item['gap_title'],
                'gap_description': item['gap_description'],
                'competitor_count': item['competitor_count'],
                'avg_views': item['avg_views'],
                'example_videos': json.dumps(item['example_videos']),
                'recommendation': item['recommendation'],
                'analyzed_week_start': week_start,
                'analyzed_week_end': week_end
            }, on_conflict='subniche,gap_title,analyzed_week_start').execute()

    print(f"[Analyzer] {len(data)} registros salvos ({analysis_type})")
