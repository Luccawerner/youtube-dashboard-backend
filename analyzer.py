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

# Stop words expandido (português + inglês + termos genéricos)
STOP_WORDS = {
    # Inglês básico
    'a', 'an', 'and', 'are', 'as', 'at', 'be', 'by', 'for', 'from', 'has', 'he',
    'in', 'is', 'it', 'its', 'of', 'on', 'that', 'the', 'to', 'was', 'will', 'with',
    'but', 'when', 'they', 'until', 'who', 'what', 'where', 'why', 'how', 'this',
    'these', 'those', 'then', 'than', 'have', 'had', 'been', 'being', 'do', 'does',
    'did', 'or', 'if', 'can', 'could', 'would', 'should', 'may', 'might', 'not',

    # Português básico
    'o', 'a', 'os', 'as', 'de', 'da', 'do', 'das', 'dos', 'em', 'no', 'na', 'nos',
    'nas', 'por', 'para', 'com', 'sem', 'sob', 'sobre', 'um', 'uma', 'uns', 'umas',
    'e', 'ou', 'mas', 'que', 'se', 'quando', 'como', 'onde', 'porque', 'qual',
    'meu', 'minha', 'meus', 'minhas', 'seu', 'sua', 'seus', 'suas',

    # Termos genéricos de vídeo
    'music', 'video', 'channel', 'new', 'best', 'top', 'hour', 'hours', 'minute',
    'minutes', 'full', 'hd', 'hq', '1080p', '720p', '4k', '2024', '2023', '2022',
    '2025', 'watch', 'subscribe', 'like', 'comment', 'share', 'playlist', 'official',
    'vídeo', 'canal', 'completo', 'novo', 'nova', 'melhor', 'melhores'
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
        Analisa keywords mais frequentes nos títulos dos vídeos (apenas vídeos 50k+ views)

        Args:
            period_days: Período em dias (7, 15 ou 30)

        Returns:
            Lista com top 10 keywords ordenadas por frequência × performance
        """
        print(f"[Analyzer] Analisando keywords (últimos {period_days} dias, 50k+ views)...")

        # Buscar vídeos do período (publicados nos últimos X dias com 50k+ views)
        cutoff_date = datetime.now() - timedelta(days=period_days)

        response = self.db.table("videos_historico")\
            .select("video_id, titulo, views_atuais, data_publicacao")\
            .gte("data_publicacao", cutoff_date.strftime("%Y-%m-%d"))\
            .gte("views_atuais", 50000)\
            .execute()

        videos = response.data

        if not videos:
            print("[Analyzer] Nenhum vídeo encontrado no período com 50k+ views")
            return []

        print(f"[Analyzer] {len(videos)} vídeos encontrados com 50k+ views")

        # Extrair keywords de todos os títulos
        keyword_stats = {}  # {keyword: {'count': int, 'total_views': int, 'video_ids': set}}

        for video in videos:
            titulo = video.get('titulo', '').lower()
            views = video.get('views_atuais', 0)
            video_id = video.get('video_id', '')

            # Extrair palavras (remover números, pontuação)
            words = re.findall(r'\b[a-zà-ú]{3,}\b', titulo)  # Suporta acentos

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
                keyword_stats[word]['videos'].add(video_id)

        # Calcular score e ordenar
        keyword_list = []
        for keyword, stats in keyword_stats.items():
            avg_views = stats['total_views'] // stats['count'] if stats['count'] > 0 else 0
            video_count = len(stats['videos'])

            # Score: frequência × sqrt(views médias) - favorece keywords com boa performance
            score = stats['count'] * (avg_views ** 0.5)

            keyword_list.append({
                'keyword': keyword,
                'frequency': stats['count'],
                'avg_views': avg_views,
                'video_count': video_count,
                'score': score
            })

        # Ordenar por score e pegar top 10
        keyword_list.sort(key=lambda x: x['score'], reverse=True)
        top_10 = keyword_list[:10]

        print(f"[Analyzer] Top {len(top_10)} keywords identificadas")
        return top_10

    # =========================================================================
    # ANÁLISE DE PADRÕES DE TÍTULO - DETECÇÃO AUTOMÁTICA GRATUITA
    # =========================================================================

    # Dicionários de categorização de palavras (expandível por subniche)
    CATEGORIAS_PALAVRAS = {
        'RELAÇÃO FAMILIAR': [
            'marido', 'esposa', 'mulher', 'esposo', 'filho', 'filha', 'filhos',
            'pai', 'mãe', 'pais', 'sogro', 'sogra', 'sogros', 'irmão', 'irmã',
            'tio', 'tia', 'avô', 'avó', 'neto', 'neta', 'primo', 'prima',
            'cunhado', 'cunhada', 'genro', 'nora', 'padrasto', 'madrasta',
            'família', 'parente', 'parentes'
        ],
        'TRAGÉDIA': [
            'faleceu', 'morreu', 'morte', 'morre', 'funeral', 'enterro',
            'acidente', 'tragédia', 'doença', 'câncer', 'hospital',
            'assassinato', 'assassinada', 'desapareceu', 'partiu', 'falecimento'
        ],
        'HERANÇA': [
            'herdou', 'herança', 'herdeira', 'testamento', 'bens', 'patrimônio',
            'deixou', 'legado', 'fortuna'
        ],
        'INJUSTIÇA': [
            'injustiça', 'injusto', 'traiu', 'traição', 'abandonou',
            'expulsou', 'roubou', 'enganou', 'mentiu', 'excluiu',
            'humilhou', 'desprezou', 'ignorou', 'restou', 'sobrou'
        ],
        'EMOÇÃO FORTE': [
            'furioso', 'furiosa', 'chocado', 'chorou', 'gritou',
            'explodiu', 'revoltado', 'desesperado', 'arrasado'
        ],
        'REVIRAVOLTA': [
            'desapareci', 'fugi', 'saí', 'abandonei', 'vinguei',
            'revelei', 'descobri', 'confessei', 'então'
        ],
        'CITAÇÃO': ['disse', 'falou', 'gritou', 'perguntou', 'respondeu'],
        'DURAÇÃO': ['hours', 'hour', 'horas', 'minutos', 'minutes', 'mins'],
        'GÊNERO MUSICAL': ['jazz', 'blues', 'lofi', 'rock', 'classical', 'piano', 'guitar'],
        'CONTEXTO USO': ['study', 'sleep', 'relax', 'work', 'estudar', 'dormir', 'relaxar'],
        'FREQUÊNCIA': ['hz', 'hertz', '432hz', '528hz', '639hz'],
        'BENEFÍCIO': ['healing', 'meditation', 'peace', 'calm', 'energia', 'cura']
    }

    def analyze_title_patterns(self, subniche: str, period_days: int = 30) -> List[Dict]:
        """
        Detecta padrões de título automaticamente (GRATUITO - sem IA)

        Estratégia:
        1. Busca vídeos com 50k+ views (publicados últimos 30 dias)
        2. Prioriza dados coletados nos últimos 7 dias (performance recente)
        3. Analisa estrutura: categoriza palavras, detecta CAPS, dinheiro, citações
        4. Agrupa títulos similares por características
        5. Retorna top 5 padrões com estrutura simples: [CAT1] + [CAT2] + [CAT3]

        Args:
            subniche: Subniche a analisar
            period_days: Período em dias (7, 15 ou 30)

        Returns:
            Lista com top 5 padrões: structure, example_title, avg_views, video_count
        """
        print(f"[Analyzer] Analisando padrões de título ({subniche}, {period_days} dias, 50k+ views)...")

        # PRIORIDADE 1: Vídeos com dados coletados nos últimos 7 dias
        cutoff_publication = datetime.now() - timedelta(days=30)  # Publicados últimos 30 dias
        cutoff_collection = datetime.now() - timedelta(days=7)   # Coletados últimos 7 dias

        response_recent = self.db.table("videos_historico")\
            .select("video_id, titulo, views_atuais, data_publicacao, data_coleta, canais_monitorados!inner(subnicho)")\
            .eq("canais_monitorados.subnicho", subniche)\
            .gte("data_publicacao", cutoff_publication.strftime("%Y-%m-%d"))\
            .gte("data_coleta", cutoff_collection.strftime("%Y-%m-%d"))\
            .gte("views_atuais", 50000)\
            .order("views_atuais", desc=True)\
            .limit(50)\
            .execute()

        videos = response_recent.data

        # Se temos poucos vídeos recentes, complementa com últimos 30 dias
        if len(videos) < 20:
            response_older = self.db.table("videos_historico")\
                .select("video_id, titulo, views_atuais, data_publicacao, data_coleta, canais_monitorados!inner(subnicho)")\
                .eq("canais_monitorados.subnicho", subniche)\
                .gte("data_publicacao", cutoff_publication.strftime("%Y-%m-%d"))\
                .gte("views_atuais", 50000)\
                .order("views_atuais", desc=True)\
                .limit(50)\
                .execute()

            # Mescla sem duplicar
            existing_ids = {v['video_id'] for v in videos}
            for v in response_older.data:
                if v['video_id'] not in existing_ids:
                    videos.append(v)

        if not videos:
            print(f"[Analyzer] Nenhum vídeo 50k+ encontrado para {subniche}")
            return []

        print(f"[Analyzer] {len(videos)} vídeos encontrados para análise")

        # Analisa estrutura de cada título
        analyzed_titles = []
        for video in videos:
            features = self._analyze_title_structure(video['titulo'])
            features['titulo'] = video['titulo']
            features['views'] = video['views_atuais']
            features['video_id'] = video['video_id']
            analyzed_titles.append(features)

        # Agrupa por estrutura similar e extrai padrões
        patterns = self._group_by_pattern(analyzed_titles)

        # Ordena por performance e retorna top 5
        patterns.sort(key=lambda x: x['avg_views'], reverse=True)
        top_5 = patterns[:5]

        print(f"[Analyzer] {len(top_5)} padrões identificados para {subniche}")
        return top_5

    def _analyze_title_structure(self, titulo: str) -> Dict:
        """Analisa características estruturais de um título"""

        features = {
            'categorias': [],  # Categorias detectadas (FAMÍLIA, TRAGÉDIA, etc)
            'has_money': False,
            'money_value': None,
            'has_caps': False,
            'caps_words': [],
            'has_quote': False,
            'has_suspense': False,
            'has_exclamation': False,
            'word_count': len(titulo.split())
        }

        titulo_lower = titulo.lower()

        # Detecta categorias de palavras
        for categoria, palavras in self.CATEGORIAS_PALAVRAS.items():
            for palavra in palavras:
                if palavra in titulo_lower:
                    if categoria not in features['categorias']:
                        features['categorias'].append(categoria)
                    break

        # Detecta dinheiro
        money_patterns = [
            r'R\$\s*\d+(?:\.\d+)?\s*(?:milhões?|mil)?',
            r'\d+\s*milhões?\s*de\s*reais',
            r'\d+\s*mil\s*reais'
        ]
        for pattern in money_patterns:
            match = re.search(pattern, titulo, re.I)
            if match:
                features['has_money'] = True
                features['money_value'] = match.group()
                break

        # Detecta CAPS (palavras em maiúsculas)
        caps_words = re.findall(r'\b[A-ZÁÉÍÓÚÂÊÔÃÕÇ]{3,}\b', titulo)
        if caps_words:
            features['has_caps'] = True
            features['caps_words'] = caps_words

        # Detecta citação (aspas, travessão)
        if re.search(r'["\'].*["\']|—|"|"', titulo):
            features['has_quote'] = True

        # Detecta suspense (reticências)
        if re.search(r'\.{2,}|…', titulo):
            features['has_suspense'] = True

        # Detecta exclamação
        if '!' in titulo:
            features['has_exclamation'] = True

        return features

    def _group_by_pattern(self, analyzed_titles: List[Dict]) -> List[Dict]:
        """Agrupa títulos por estrutura similar e extrai padrões"""

        patterns = []

        # Agrupa por combinações de categorias
        category_groups = {}

        for item in analyzed_titles:
            # Cria chave baseada nas categorias (ordenadas)
            cats = sorted(item['categorias'])
            if not cats:
                continue

            key = tuple(cats)

            if key not in category_groups:
                category_groups[key] = []

            category_groups[key].append(item)

        # Para cada grupo, cria um padrão
        for categories_tuple, items in category_groups.items():
            if len(items) < 3:  # Mínimo 3 vídeos para ser considerado padrão
                continue

            # Calcula métricas
            avg_views = sum(item['views'] for item in items) // len(items)
            best_item = max(items, key=lambda x: x['views'])

            # Monta estrutura do padrão
            structure_parts = list(categories_tuple)

            # Adiciona características especiais se presentes na maioria
            money_count = sum(1 for i in items if i['has_money'])
            caps_count = sum(1 for i in items if i['has_caps'])
            quote_count = sum(1 for i in items if i['has_quote'])
            suspense_count = sum(1 for i in items if i['has_suspense'])

            total = len(items)

            if money_count / total >= 0.6:  # 60%+ tem dinheiro
                if 'HERANÇA' not in structure_parts:
                    structure_parts.append('VALOR FINANCEIRO')

            if quote_count / total >= 0.6:  # 60%+ tem citação
                if 'CITAÇÃO' not in structure_parts:
                    structure_parts.insert(min(2, len(structure_parts)), 'CITAÇÃO DIRETA')

            if suspense_count / total >= 0.6:  # 60%+ tem suspense
                structure_parts.append('SUSPENSE')

            # Monta estrutura final
            structure = ' + '.join([f'[{part}]' for part in structure_parts])

            patterns.append({
                'pattern_structure': structure,
                'example_title': best_item['titulo'],
                'avg_views': avg_views,
                'video_count': len(items)
            })

        return patterns

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

        # Calcular inscritos ganhos (mês atual e mês anterior)
        for canal_id, data in channels_by_id.items():
            current_subs = data['inscritos']

            # Buscar snapshot de 30 dias atrás (início do mês atual)
            date_30d_ago = datetime.now() - timedelta(days=30)
            response_30d = self.db.table("dados_canais_historico")\
                .select("inscritos")\
                .eq("canal_id", canal_id)\
                .lte("data_coleta", date_30d_ago.strftime("%Y-%m-%d"))\
                .order("data_coleta", desc=True)\
                .limit(1)\
                .execute()

            subs_30d_ago = response_30d.data[0]['inscritos'] if response_30d.data else current_subs
            data['subscribers_gained_30d'] = current_subs - subs_30d_ago

            # Buscar snapshot de 60 dias atrás (início do mês anterior)
            date_60d_ago = datetime.now() - timedelta(days=60)
            response_60d = self.db.table("dados_canais_historico")\
                .select("inscritos")\
                .eq("canal_id", canal_id)\
                .lte("data_coleta", date_60d_ago.strftime("%Y-%m-%d"))\
                .order("data_coleta", desc=True)\
                .limit(1)\
                .execute()

            subs_60d_ago = response_60d.data[0]['inscritos'] if response_60d.data else subs_30d_ago

            # Inscritos ganhos no mês anterior (60-30 dias atrás)
            data['subscribers_previous_month'] = subs_30d_ago - subs_60d_ago

            # Crescimento percentual (mês atual vs mês anterior)
            if data['subscribers_previous_month'] > 0:
                growth = ((data['subscribers_gained_30d'] - data['subscribers_previous_month']) / data['subscribers_previous_month']) * 100
                data['growth_percentage'] = round(growth, 1)
            else:
                data['growth_percentage'] = 0.0

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
            .select("*, canais_monitorados!inner(subnicho, tipo)")\
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
