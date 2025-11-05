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
    # Inglês básico - artigos, preposições, conjunções
    'a', 'an', 'and', 'are', 'as', 'at', 'be', 'by', 'for', 'from', 'has', 'he', 'she',
    'in', 'is', 'it', 'its', 'of', 'on', 'that', 'the', 'to', 'was', 'will', 'with',
    'but', 'when', 'they', 'until', 'who', 'what', 'where', 'why', 'how', 'this',
    'these', 'those', 'then', 'than', 'have', 'had', 'been', 'being', 'do', 'does',
    'did', 'or', 'if', 'can', 'could', 'would', 'should', 'may', 'might', 'not',
    'we', 'us', 'our', 'ours', 'you', 'your', 'yours', 'him', 'his', 'her', 'hers',
    'them', 'their', 'theirs', 'me', 'my', 'mine', 'myself', 'yourself', 'himself',
    'herself', 'itself', 'ourselves', 'themselves',

    # Verbos comuns (não são keywords relevantes)
    'said', 'told', 'asked', 'gave', 'made', 'went', 'got', 'took', 'came', 'put',
    'thought', 'looked', 'wanted', 'used', 'found', 'knew', 'called', 'tried',
    'left', 'felt', 'became', 'seemed', 'turned', 'kept', 'began', 'brought',
    'happened', 'showed', 'heard', 'needed', 'moved', 'lived', 'believed', 'held',
    'saw', 'let', 'met', 'ran', 'paid', 'sat', 'spoke', 'stood', 'understood',

    # Português básico
    'o', 'a', 'os', 'as', 'de', 'da', 'do', 'das', 'dos', 'em', 'no', 'na', 'nos',
    'nas', 'por', 'para', 'com', 'sem', 'sob', 'sobre', 'um', 'uma', 'uns', 'umas',
    'e', 'ou', 'mas', 'que', 'se', 'quando', 'como', 'onde', 'porque', 'qual',
    'meu', 'minha', 'meus', 'minhas', 'seu', 'sua', 'seus', 'suas', 'ele', 'ela',
    'eles', 'elas', 'nós', 'vós', 'lhe', 'lhes', 'me', 'te', 'nos', 'vos',

    # Verbos comuns português
    'disse', 'falou', 'fez', 'foi', 'era', 'tinha', 'estava', 'fui', 'deu', 'viu',
    'sabia', 'pode', 'podia', 'deve', 'quer', 'quis', 'sabe', 'vai', 'vou', 'tem',
    'ser', 'estar', 'ter', 'fazer', 'dar', 'ver', 'saber', 'poder', 'dever', 'querer',

    # Termos genéricos de vídeo
    'music', 'video', 'channel', 'new', 'best', 'top', 'hour', 'hours', 'minute',
    'minutes', 'full', 'hd', 'hq', '1080p', '720p', '4k', '2024', '2023', '2022',
    '2025', 'watch', 'subscribe', 'like', 'comment', 'share', 'playlist', 'official',
    'vídeo', 'canal', 'completo', 'novo', 'nova', 'melhor', 'melhores', 'compilation'
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
        Analisa keywords mais frequentes nos títulos dos vídeos (apenas vídeos VIRAIS 100k+ views)

        Args:
            period_days: Período em dias (7, 15 ou 30)

        Returns:
            Lista com top 10 keywords ordenadas por performance (views médias)
        """
        print(f"[Analyzer] Analisando keywords (últimos {period_days} dias, 100k+ views virais)...")

        # Buscar vídeos do período (publicados nos últimos X dias com 100k+ views - VIRAIS!)
        cutoff_date = datetime.now() - timedelta(days=period_days)

        response = self.db.table("videos_historico")\
            .select("video_id, titulo, views_atuais, data_publicacao")\
            .gte("data_publicacao", cutoff_date.strftime("%Y-%m-%d"))\
            .gte("views_atuais", 100000)\
            .execute()

        videos = response.data

        if not videos:
            print("[Analyzer] Nenhum vídeo encontrado no período com 100k+ views")
            return []

        print(f"[Analyzer] {len(videos)} vídeos virais encontrados (100k+ views)")

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
            video_count = len(stats['videos'])

            # CORREÇÃO: avg_views = total / número de VÍDEOS únicos (não ocorrências)
            avg_views = stats['total_views'] // video_count if video_count > 0 else 0

            # Score: performance médias ** 0.7 × √(vídeos únicos) - prioriza keywords com alta performance
            score = (avg_views ** 0.7) * (video_count ** 0.5)

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

    # Dicionários de categorização SEPARADOS por tipo de conteúdo
    CATEGORIAS_STORYTELLING = {
        'RELAÇÃO FAMILIAR': [
            'marido', 'esposa', 'mulher', 'esposo', 'husband', 'wife',
            'filho', 'filha', 'filhos', 'son', 'daughter', 'children',
            'pai', 'mãe', 'pais', 'father', 'mother', 'parents', 'dad', 'mom',
            'sogro', 'sogra', 'sogros', 'father-in-law', 'mother-in-law',
            'irmão', 'irmã', 'brother', 'sister', 'siblings',
            'tio', 'tia', 'uncle', 'aunt',
            'avô', 'avó', 'grandfather', 'grandmother', 'grandparents',
            'neto', 'neta', 'grandson', 'granddaughter',
            'primo', 'prima', 'cousin',
            'cunhado', 'cunhada', 'genro', 'nora',
            'padrasto', 'madrasta', 'stepfather', 'stepmother',
            'família', 'parente', 'parentes', 'family', 'relative'
        ],
        'TRAGÉDIA': [
            'faleceu', 'morreu', 'morte', 'died', 'death', 'passed', 'funeral',
            'enterro', 'velório', 'burial',
            'acidente', 'tragédia', 'accident', 'tragedy',
            'doença', 'câncer', 'hospital', 'disease', 'cancer', 'illness',
            'assassinato', 'assassinada', 'murder', 'killed',
            'desapareceu', 'disappeared', 'missing'
        ],
        'HERANÇA': [
            'herdou', 'herança', 'herdeira', 'inherited', 'inheritance', 'heir',
            'testamento', 'will', 'testament',
            'bens', 'patrimônio', 'property', 'estate',
            'deixou', 'legado', 'left', 'legacy',
            'fortuna', 'fortune', 'wealth'
        ],
        'INJUSTIÇA': [
            'injustiça', 'injusto', 'injustice', 'unfair',
            'traiu', 'traição', 'betrayed', 'betrayal', 'cheated',
            'abandonou', 'abandoned', 'left',
            'expulsou', 'kicked', 'expelled',
            'roubou', 'roubo', 'stole', 'robbed', 'theft',
            'enganou', 'mentiu', 'mentira', 'lied', 'deceived', 'lie',
            'excluiu', 'excluded',
            'humilhou', 'humilhação', 'humiliated',
            'desprezou', 'desprezo', 'ignored', 'rejected',
            'restou', 'sobrou', 'left with'
        ],
        'EMOÇÃO FORTE': [
            'furioso', 'furiosa', 'fúria', 'furious', 'angry', 'rage',
            'chocado', 'chocada', 'choque', 'shocked', 'stunned',
            'chorou', 'choro', 'chorando', 'cried', 'crying', 'tears',
            'gritou', 'grito', 'gritando', 'screamed', 'yelled', 'shouted',
            'explodiu', 'explosão', 'exploded',
            'revoltado', 'revolta', 'revolted',
            'desesperado', 'desespero', 'desperate',
            'arrasado', 'arrasada', 'devastated'
        ],
        'REVIRAVOLTA': [
            'desapareci', 'disappeared',
            'fugi', 'fuga', 'ran', 'escape',
            'saí', 'left',
            'abandonei', 'vinguei', 'vingança', 'revenge',
            'revelei', 'revelação', 'revealed',
            'descobri', 'descoberta', 'discovered', 'found',
            'confessei', 'confissão', 'confessed',
            'então', 'then', 'but'
        ],
        'CITAÇÃO': [
            'disse', 'falou', 'said', 'told',
            'gritou', 'screamed', 'yelled',
            'perguntou', 'asked',
            'respondeu', 'replied'
        ],
        'SEGREDO': [
            'segredo', 'secret', 'hidden',
            'escondido', 'oculto',
            'verdade', 'truth',
            'mistério', 'mystery'
        ],
        'CONFLITO': [
            'briga', 'fight', 'argument',
            'discussão', 'dispute',
            'guerra', 'war',
            'problema', 'problem'
        ]
    }

    CATEGORIAS_MUSICA = {
        'DURAÇÃO': ['hours', 'hour', 'horas', 'hora', 'minutos', 'minutes', 'mins'],
        'GÊNERO MUSICAL': [
            'jazz', 'blues', 'lofi', 'lo-fi', 'rock', 'classical', 'pop',
            'piano', 'guitar', 'saxophone', 'violin', 'instrumental'
        ],
        'CONTEXTO USO': [
            'study', 'sleep', 'relax', 'work', 'focus', 'meditation',
            'estudar', 'dormir', 'relaxar', 'trabalhar', 'focar'
        ],
        'FREQUÊNCIA': ['hz', 'hertz', '432hz', '528hz', '639hz', '741hz'],
        'BENEFÍCIO': [
            'healing', 'meditation', 'peace', 'calm', 'calming',
            'energia', 'cura', 'relaxamento', 'peaceful'
        ],
        'AMBIENTE': [
            'rainy', 'rain', 'snowy', 'winter', 'summer', 'night', 'morning',
            'cozy', 'chill', 'relaxing', 'smooth', 'soft'
        ]
    }

    CATEGORIAS_HISTORIA = {
        'TEMA HISTÓRICO': [
            'ancient', 'history', 'civilization', 'empire', 'kingdom',
            'war', 'battle', 'medieval', 'renaissance',
            'antiguidade', 'história', 'civilização', 'império', 'reino'
        ],
        'MISTÉRIO': [
            'mystery', 'unsolved', 'secret', 'hidden', 'unknown',
            'mistério', 'inexplicável', 'desconhecido'
        ],
        'DESCOBERTA': [
            'discovered', 'found', 'revealed', 'uncovered',
            'descoberta', 'revelação', 'achado'
        ]
    }

    def _get_subniche_type(self, subniche: str) -> str:
        """
        Determina o tipo de conteúdo baseado no subniche

        Returns:
            'storytelling', 'music' ou 'history'
        """
        storytelling_niches = [
            'Contos Familiares', 'Histórias Motivacionais', 'Histórias Sombrias',
            'Histórias Aleatórias', 'Storytelling', 'Contos'
        ]

        music_niches = [
            'Jazz', 'Blues', 'Lofi', 'Classical', 'Piano', 'Focus',
            'Música', 'Music', 'Frequencies', 'Frequências', 'Meditação', 'Meditation'
        ]

        history_niches = [
            'Antiguidade', 'História Antiga', 'Civilizações', 'History',
            'Ancient', 'Mistérios', 'Mysteries'
        ]

        if subniche in storytelling_niches:
            return 'storytelling'
        elif subniche in music_niches:
            return 'music'
        elif subniche in history_niches:
            return 'history'
        else:
            # Default para storytelling (maioria dos nossos canais)
            return 'storytelling'

    def analyze_title_patterns(self, subniche: str, period_days: int = 30) -> List[Dict]:
        """
        Detecta padrões de título automaticamente (GRATUITO - sem IA)

        Estratégia:
        1. Busca vídeos com 30k+ views (publicados últimos 30 dias)
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
        print(f"[Analyzer] Analisando padrões de título ({subniche}, {period_days} dias, 30k+ views)...")

        # PRIORIDADE 1: Vídeos com dados coletados nos últimos 7 dias
        cutoff_publication = datetime.now() - timedelta(days=30)  # Publicados últimos 30 dias
        cutoff_collection = datetime.now() - timedelta(days=7)   # Coletados últimos 7 dias

        response_recent = self.db.table("videos_historico")\
            .select("video_id, titulo, views_atuais, data_publicacao, data_coleta, canais_monitorados!inner(subnicho)")\
            .eq("canais_monitorados.subnicho", subniche)\
            .gte("data_publicacao", cutoff_publication.strftime("%Y-%m-%d"))\
            .gte("data_coleta", cutoff_collection.strftime("%Y-%m-%d"))\
            .gte("views_atuais", 30000)\
            .order("views_atuais", desc=True)\
            .limit(100)\
            .execute()

        videos = response_recent.data

        # Se temos poucos vídeos recentes, complementa com últimos 30 dias
        if len(videos) < 20:
            response_older = self.db.table("videos_historico")\
                .select("video_id, titulo, views_atuais, data_publicacao, data_coleta, canais_monitorados!inner(subnicho)")\
                .eq("canais_monitorados.subnicho", subniche)\
                .gte("data_publicacao", cutoff_publication.strftime("%Y-%m-%d"))\
                .gte("views_atuais", 30000)\
                .order("views_atuais", desc=True)\
                .limit(100)\
                .execute()

            # Mescla sem duplicar
            existing_ids = {v['video_id'] for v in videos}
            for v in response_older.data:
                if v['video_id'] not in existing_ids:
                    videos.append(v)

        if not videos:
            print(f"[Analyzer] Nenhum vídeo 30k+ encontrado para {subniche}")
            return []

        print(f"[Analyzer] {len(videos)} vídeos encontrados para análise")

        # Analisa estrutura de cada título
        analyzed_titles = []
        for video in videos:
            features = self._analyze_title_structure(video['titulo'], subniche)
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

    def _analyze_title_structure(self, titulo: str, subniche: str) -> Dict:
        """
        Analisa características estruturais de um título

        Args:
            titulo: Título do vídeo
            subniche: Subniche para determinar tipo de conteúdo

        Returns:
            Dict com features detectadas
        """
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

        # Seleciona dicionário de categorias baseado no tipo de subniche
        subniche_type = self._get_subniche_type(subniche)

        if subniche_type == 'storytelling':
            categories_dict = self.CATEGORIAS_STORYTELLING
        elif subniche_type == 'music':
            categories_dict = self.CATEGORIAS_MUSICA
        else:  # history
            categories_dict = self.CATEGORIAS_HISTORIA

        # Detecta categorias de palavras usando o dicionário correto
        for categoria, palavras in categories_dict.items():
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
            if len(items) < 2:  # Mínimo 2 vídeos para ser considerado padrão
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
        Identifica gaps ESTRATÉGICOS (o que concorrentes fazem que nós não fazemos)

        Analisa 4 dimensões:
        1. Duração dos vídeos
        2. Frequência de upload
        3. Taxa de engagement (likes/views)
        4. Padrões de título (menos prioritário)

        Args:
            subniche: Subniche a analisar

        Returns:
            Lista com no máximo 2 gaps mais importantes
        """
        print(f"[Analyzer] Analisando gaps ESTRATÉGICOS ({subniche})...")

        gaps = []
        cutoff_date = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")

        # =====================================================================
        # GAP 1: DURAÇÃO DOS VÍDEOS
        # =====================================================================
        print(f"[Analyzer] Analisando gap de duração...")

        # Nossos vídeos (30k+ views, últimos 30 dias)
        response_nossos = self.db.table("videos_historico")\
            .select("duracao, canais_monitorados!inner(tipo, subnicho)")\
            .eq("canais_monitorados.tipo", "nosso")\
            .eq("canais_monitorados.subnicho", subniche)\
            .gte("data_publicacao", cutoff_date)\
            .gte("views_atuais", 30000)\
            .execute()

        nossos_videos = response_nossos.data

        # Concorrentes (30k+ views, últimos 30 dias)
        response_concorrentes = self.db.table("videos_historico")\
            .select("duracao, canais_monitorados!inner(tipo, subnicho)")\
            .eq("canais_monitorados.tipo", "minerado")\
            .eq("canais_monitorados.subnicho", subniche)\
            .gte("data_publicacao", cutoff_date)\
            .gte("views_atuais", 30000)\
            .execute()

        concorrentes_videos = response_concorrentes.data

        if nossos_videos and concorrentes_videos:
            # Calcula duração média (em segundos)
            nossos_durations = [v.get('duracao', 0) for v in nossos_videos if v.get('duracao', 0) > 0]
            concorrentes_durations = [v.get('duracao', 0) for v in concorrentes_videos if v.get('duracao', 0) > 0]

            if nossos_durations and concorrentes_durations:
                nossa_avg_duration = sum(nossos_durations) / len(nossos_durations)
                concorrente_avg_duration = sum(concorrentes_durations) / len(concorrentes_durations)

                # Diferença significativa (> 10min = 600s)
                diff_seconds = abs(nossa_avg_duration - concorrente_avg_duration)
                if diff_seconds > 600:
                    diff_percent = ((concorrente_avg_duration / nossa_avg_duration - 1) * 100) if nossa_avg_duration > 0 else 0

                    gaps.append({
                        'type': 'duration',
                        'priority': 'high' if diff_seconds > 1200 else 'medium',  # 20min = crítico
                        'title': 'Duração dos Vídeos',
                        'your_value': f'{int(nossa_avg_duration // 60)}min',
                        'your_context': 'média atual',
                        'competitor_value': f'{int(concorrente_avg_duration // 60)}min',
                        'competitor_context': 'top performers',
                        'difference': diff_percent,
                        'impact_description': f"+{abs(diff_percent):.0f}% {'mais longo' if concorrente_avg_duration > nossa_avg_duration else 'mais curto'} = potencial +40-60% views",
                        'actions': [
                            f"Aumentar duração para {int(concorrente_avg_duration // 60)}-{int(concorrente_avg_duration // 60) + 5}min" if concorrente_avg_duration > nossa_avg_duration else f"Reduzir duração para {int(concorrente_avg_duration // 60)}-{int(concorrente_avg_duration // 60) + 5}min",
                            "Analisar vídeos top do subniche: quanto tempo duram?",
                            "Manter qualidade - não encher de conteúdo fraco"
                        ],
                        'priority_text': 'ALTA' if diff_seconds > 1200 else 'MÉDIA',
                        'effort': 'Médio',
                        'roi': '+40-60% views estimado'
                    })

        # =====================================================================
        # GAP 2: FREQUÊNCIA DE UPLOAD
        # =====================================================================
        print(f"[Analyzer] Analisando gap de frequência...")

        # Contar vídeos por canal (nossos)
        response_nossos_canais = self.db.table("videos_historico")\
            .select("canal_id, canais_monitorados!inner(tipo, subnicho)")\
            .eq("canais_monitorados.tipo", "nosso")\
            .eq("canais_monitorados.subnicho", subniche)\
            .gte("data_publicacao", cutoff_date)\
            .execute()

        nossos_canais_videos = response_nossos_canais.data

        # Contar vídeos por canal (concorrentes)
        response_concorrentes_canais = self.db.table("videos_historico")\
            .select("canal_id, canais_monitorados!inner(tipo, subnicho)")\
            .eq("canais_monitorados.tipo", "minerado")\
            .eq("canais_monitorados.subnicho", subniche)\
            .gte("data_publicacao", cutoff_date)\
            .execute()

        concorrentes_canais_videos = response_concorrentes_canais.data

        if nossos_canais_videos and concorrentes_canais_videos:
            # Calcular vídeos/canal
            nossos_canais_unique = set([v['canal_id'] for v in nossos_canais_videos])
            concorrentes_canais_unique = set([v['canal_id'] for v in concorrentes_canais_videos])

            nossa_freq = len(nossos_canais_videos) / len(nossos_canais_unique) if nossos_canais_unique else 0
            concorrente_freq = len(concorrentes_canais_videos) / len(concorrentes_canais_unique) if concorrentes_canais_unique else 0

            # Diferença significativa (> 2 vídeos/mês)
            diff_videos = abs(nossa_freq - concorrente_freq)
            if diff_videos > 2:
                diff_percent = ((concorrente_freq / nossa_freq - 1) * 100) if nossa_freq > 0 else 0

                gaps.append({
                    'type': 'frequency',
                    'priority': 'high' if diff_videos > 4 else 'medium',
                    'title': 'Frequência de Upload',
                    'your_value': f'{nossa_freq:.1f} vídeos/mês',
                    'your_context': 'inconsistente' if nossa_freq < 4 else 'atual',
                    'competitor_value': f'{concorrente_freq:.1f} vídeos/mês',
                    'competitor_context': 'consistente',
                    'difference': diff_percent,
                    'impact_description': f"+{abs(diff_percent):.0f}% mais conteúdo = algoritmo favorece +80-120% crescimento",
                    'actions': [
                        f"Passar de {nossa_freq:.1f} para {concorrente_freq:.1f} vídeos/mês" if concorrente_freq > nossa_freq else f"Reduzir frequência e focar em qualidade",
                        "Automatizar produção ou contratar editor adicional" if concorrente_freq > nossa_freq else "Analisar quais vídeos performam melhor",
                        "Manter consistência - postar em dias fixos"
                    ],
                    'priority_text': 'ALTA' if diff_videos > 4 else 'MÉDIA',
                    'effort': 'Alto' if concorrente_freq > nossa_freq else 'Baixo',
                    'roi': '+80-120% crescimento estimado' if concorrente_freq > nossa_freq else '+20-40% qualidade'
                })

        # =====================================================================
        # GAP 3: TAXA DE ENGAGEMENT (LIKES/VIEWS)
        # =====================================================================
        print(f"[Analyzer] Analisando gap de engagement...")

        # Nossos vídeos com likes
        response_nossos_eng = self.db.table("videos_historico")\
            .select("views_atuais, likes_atuais, canais_monitorados!inner(tipo, subnicho)")\
            .eq("canais_monitorados.tipo", "nosso")\
            .eq("canais_monitorados.subnicho", subniche)\
            .gte("data_publicacao", cutoff_date)\
            .gte("views_atuais", 10000)\
            .execute()

        nossos_eng = response_nossos_eng.data

        # Concorrentes com likes
        response_concorrentes_eng = self.db.table("videos_historico")\
            .select("views_atuais, likes_atuais, canais_monitorados!inner(tipo, subnicho)")\
            .eq("canais_monitorados.tipo", "minerado")\
            .eq("canais_monitorados.subnicho", subniche)\
            .gte("data_publicacao", cutoff_date)\
            .gte("views_atuais", 10000)\
            .execute()

        concorrentes_eng = response_concorrentes_eng.data

        if nossos_eng and concorrentes_eng:
            # Calcular engagement rate (%)
            nossa_eng_rate = sum([
                (v.get('likes_atuais', 0) / v['views_atuais'] * 100)
                for v in nossos_eng if v['views_atuais'] > 0
            ]) / len(nossos_eng)

            concorrente_eng_rate = sum([
                (v.get('likes_atuais', 0) / v['views_atuais'] * 100)
                for v in concorrentes_eng if v['views_atuais'] > 0
            ]) / len(concorrentes_eng)

            # Diferença significativa (> 0.5%)
            diff_eng = abs(nossa_eng_rate - concorrente_eng_rate)
            if diff_eng > 0.5:
                diff_percent = ((concorrente_eng_rate / nossa_eng_rate - 1) * 100) if nossa_eng_rate > 0 else 0

                gaps.append({
                    'type': 'engagement',
                    'priority': 'high' if diff_eng > 1.0 else 'medium',
                    'title': 'Taxa de Engagement (Likes/Views)',
                    'your_value': f'{nossa_eng_rate:.2f}%',
                    'your_context': f'{int(nossa_eng_rate * 400)} likes/40k views',
                    'competitor_value': f'{concorrente_eng_rate:.2f}%',
                    'competitor_context': f'{int(concorrente_eng_rate * 400)} likes/40k views',
                    'difference': diff_percent,
                    'impact_description': f"+{abs(diff_percent):.0f}% engagement = algoritmo favorece +30-50% alcance",
                    'actions': [
                        "Adicionar CTAs fortes nos momentos emocionais altos",
                        "Pedir likes no início (1-2min) E final do vídeo",
                        "Responder primeiros 10 comentários em 1h (engajamento)",
                        "Analisar thumbnails dos top 5 - criar mais expectativa"
                    ],
                    'priority_text': 'ALTA' if diff_eng > 1.0 else 'MÉDIA',
                    'effort': 'Baixo',
                    'roi': '+30-50% alcance estimado'
                })

        # Ordenar por prioridade e retornar no máximo 2 gaps
        gaps.sort(key=lambda x: {'high': 0, 'medium': 1}.get(x['priority'], 2))

        print(f"[Analyzer] {len(gaps[:2])} gaps estratégicos identificados para {subniche}")
        return gaps[:2]  # MÁXIMO 2 GAPS MAIS IMPORTANTES


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
            # Primeiro, deletar registros antigos para esse subniche/period/date
            db_client.table("title_patterns").delete()\
                .eq('subniche', subniche)\
                .eq('period_days', period_days)\
                .eq('analyzed_date', today)\
                .execute()

            # Inserir novo registro
            db_client.table("title_patterns").insert({
                'subniche': subniche,
                'period_days': period_days,
                'pattern_structure': item['pattern_structure'],
                'pattern_description': '',  # Campo vazio (não usado mais)
                'example_title': item['example_title'],
                'avg_views': item['avg_views'],
                'video_count': item['video_count'],
                'analyzed_date': today
            }).execute()

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
