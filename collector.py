import os
import re
import asyncio
import logging
import html
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Optional, Any, Set
from collections import deque
import aiohttp
import json

logger = logging.getLogger(__name__)

# 🆕 FUNÇÃO PARA DECODIFICAR HTML ENTITIES
def decode_html_entities(text: str) -> str:
    """Decodifica HTML entities em texto (ex: &#39; -> ')"""
    if not text:
        return text
    return html.unescape(text)


class RateLimiter:
    """
    Rate Limiter para respeitar o limite de 100 req/100s do YouTube
    Mantém histórico de requisições e calcula automaticamente quando pode fazer nova requisição
    """
    def __init__(self, max_requests: int = 90, time_window: int = 100):
        """
        max_requests: Máximo de requisições permitidas (90 para margem de segurança)
        time_window: Janela de tempo em segundos (100s)
        """
        self.max_requests = max_requests
        self.time_window = time_window
        self.requests = deque()  # Armazena timestamps das requisições
    
    def _clean_old_requests(self):
        """Remove requisições antigas (fora da janela de 100s)"""
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(seconds=self.time_window)
        
        while self.requests and self.requests[0] < cutoff:
            self.requests.popleft()
    
    def can_make_request(self) -> bool:
        """Verifica se pode fazer uma nova requisição"""
        self._clean_old_requests()
        return len(self.requests) < self.max_requests
    
    def get_wait_time(self) -> float:
        """Calcula quanto tempo deve aguardar antes da próxima requisição"""
        self._clean_old_requests()
        
        if len(self.requests) < self.max_requests:
            return 0.0
        
        # Precisa aguardar até a requisição mais antiga sair da janela
        oldest = self.requests[0]
        now = datetime.now(timezone.utc)
        wait = (oldest + timedelta(seconds=self.time_window)) - now
        return max(0.0, wait.total_seconds())
    
    def record_request(self):
        """Registra que uma requisição foi feita"""
        self._clean_old_requests()
        self.requests.append(datetime.now(timezone.utc))
    
    async def wait_if_needed(self):
        """Aguarda automaticamente se necessário antes de fazer requisição"""
        wait_time = self.get_wait_time()
        if wait_time > 0:
            logger.info(f"⏳ Rate limit próximo - aguardando {wait_time:.1f}s")
            await asyncio.sleep(wait_time + 0.5)  # +0.5s margem extra
    
    def get_stats(self) -> Dict:
        """Retorna estatísticas do rate limiter"""
        self._clean_old_requests()
        return {
            "requests_in_window": len(self.requests),
            "max_requests": self.max_requests,
            "utilization_pct": (len(self.requests) / self.max_requests) * 100
        }


class YouTubeCollector:
    def __init__(self):
        # Busca todas as chaves de API (KEY_1 até KEY_10)
        self.api_keys = [
            os.environ.get("YOUTUBE_API_KEY_1"),
            os.environ.get("YOUTUBE_API_KEY_2"),
            os.environ.get("YOUTUBE_API_KEY_3"),
            os.environ.get("YOUTUBE_API_KEY_4"),
            os.environ.get("YOUTUBE_API_KEY_5"),
            os.environ.get("YOUTUBE_API_KEY_6"),
            os.environ.get("YOUTUBE_API_KEY_7"),
            os.environ.get("YOUTUBE_API_KEY_8"),
            os.environ.get("YOUTUBE_API_KEY_9"),
            os.environ.get("YOUTUBE_API_KEY_10")
        ]
        
        # Filtra apenas chaves que existem
        self.api_keys = [key for key in self.api_keys if key]
        
        if not self.api_keys:
            raise ValueError("At least one YouTube API key is required")
        
        # Um RateLimiter para CADA chave
        self.rate_limiters = {i: RateLimiter() for i in range(len(self.api_keys))}
        
        self.current_key_index = 0
        self.exhausted_keys = set()
        self.last_reset_date = datetime.now(timezone.utc).date()  # 🆕 Rastrear último reset
        self.base_url = "https://www.googleapis.com/youtube/v3"
        
        # REQUEST COUNTER
        self.total_requests = 0
        self.requests_per_key = {i: 0 for i in range(len(self.api_keys))}
        self.requests_per_canal: Dict[str, int] = {}
        self.failed_canals: Set[str] = set()
        
        # RETRY CONFIG
        self.max_retries = 3
        self.base_delay = 0.8  # Delay base entre requisições
        
        logger.info(f"🚀 YouTube collector initialized with {len(self.api_keys)} API keys")
        logger.info(f"📊 Rate limiter: {self.rate_limiters[0].max_requests} req/{self.rate_limiters[0].time_window}s per key")

    def reset_for_new_collection(self):
        """
        Reset collector state - RESETA exhausted_keys se passou da meia-noite UTC
        Google reseta quota à meia-noite UTC, então devemos resetar nossa flag também
        """
        self.failed_canals = set()
        self.total_requests = 0
        self.requests_per_key = {i: 0 for i in range(len(self.api_keys))}
        self.requests_per_canal = {}
        
        # 🆕 RESETAR CHAVES ESGOTADAS A CADA NOVA COLETA
        # Pois quota do Google já resetou à meia-noite UTC
        if self.exhausted_keys:
            logger.info("=" * 80)
            logger.info(f"🔄 RESETANDO {len(self.exhausted_keys)} CHAVES MARCADAS COMO ESGOTADAS")
            logger.info("✅ Quota do Google resetou à meia-noite UTC - todas chaves disponíveis novamente")
            logger.info("=" * 80)
            self.exhausted_keys.clear()
        
        logger.info("=" * 80)
        logger.info("🔄 COLLECTOR RESET")
        logger.info(f"🔑 Chaves disponíveis: {len(self.api_keys) - len(self.exhausted_keys)}/{len(self.api_keys)}")
        logger.info(f"📊 Chave atual: {self.current_key_index + 1}")
        logger.info("=" * 80)

    def increment_request_counter(self, canal_name: str = "system"):
        """Increment request counter"""
        self.total_requests += 1
        self.requests_per_key[self.current_key_index] += 1
        if canal_name not in self.requests_per_canal:
            self.requests_per_canal[canal_name] = 0
        self.requests_per_canal[canal_name] += 1
        
    def get_request_stats(self) -> Dict[str, Any]:
        """Get request statistics"""
        return {
            "total_requests": self.total_requests,
            "requests_per_key": self.requests_per_key.copy(),
            "requests_per_canal": self.requests_per_canal.copy(),
            "failed_canals": list(self.failed_canals),
            "exhausted_keys": len(self.exhausted_keys),
            "active_keys": len(self.api_keys) - len(self.exhausted_keys)
        }

    def get_current_api_key(self) -> Optional[str]:
        """Get current API key - PULA chaves esgotadas"""
        if self.all_keys_exhausted():
            return None
        
        # Pula chaves esgotadas
        attempts = 0
        while self.current_key_index in self.exhausted_keys and attempts < len(self.api_keys):
            self.current_key_index = (self.current_key_index + 1) % len(self.api_keys)
            attempts += 1
        
        if attempts >= len(self.api_keys):
            return None
            
        return self.api_keys[self.current_key_index]

    def rotate_to_next_key(self):
        """Rotaciona para próxima chave disponível (round-robin)"""
        old_index = self.current_key_index
        self.current_key_index = (self.current_key_index + 1) % len(self.api_keys)
        
        # Pula chaves esgotadas
        attempts = 0
        while self.current_key_index in self.exhausted_keys and attempts < len(self.api_keys):
            self.current_key_index = (self.current_key_index + 1) % len(self.api_keys)
            attempts += 1
        
        if old_index != self.current_key_index:
            stats = self.rate_limiters[self.current_key_index].get_stats()
            logger.info(f"🔄 Rotated: Key {old_index + 1} → Key {self.current_key_index + 1} (load: {stats['requests_in_window']}/{stats['max_requests']})")

    def mark_key_as_exhausted(self):
        """Marca chave atual como esgotada"""
        self.exhausted_keys.add(self.current_key_index)
        logger.error(f"🚨 Key {self.current_key_index + 1} EXHAUSTED (quota esgotada)")
        self.rotate_to_next_key()
    
    def all_keys_exhausted(self) -> bool:
        """Check if all API keys are exhausted"""
        return len(self.exhausted_keys) >= len(self.api_keys)

    def mark_canal_as_failed(self, canal_url: str):
        """Mark a canal as failed"""
        self.failed_canals.add(canal_url)

    def is_canal_failed(self, canal_url: str) -> bool:
        """Check if canal already failed"""
        return canal_url in self.failed_canals

    async def make_api_request(self, url: str, params: dict, canal_name: str = "system", retry_count: int = 0) -> Optional[dict]:
        """
        Função para fazer requisições à API do YouTube
        Gerencia rate limiting, retries, e diferenciação de erros
        """
        if self.all_keys_exhausted():
            logger.error("❌ All keys exhausted!")
            return None
        
        current_key = self.get_current_api_key()
        if not current_key:
            return None
        
        params['key'] = current_key
        
        # AGUARDA RATE LIMITER
        await self.rate_limiters[self.current_key_index].wait_if_needed()
        
        try:
            async with aiohttp.ClientSession() as session:
                # Incrementa contadores ANTES da requisição
                self.increment_request_counter(canal_name)
                self.rate_limiters[self.current_key_index].record_request()
                
                # Delay base
                if self.total_requests > 0:
                    await asyncio.sleep(self.base_delay)
                
                async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=30)) as response:
                    
                    # ✅ SUCESSO
                    if response.status == 200:
                        data = await response.json()
                        return data
                    
                    # ⚠️ ERRO 403 - TRATAMENTO MELHORADO
                    elif response.status == 403:
                        error_data = await response.json()
                        error_obj = error_data.get('error', {})
                        error_msg = error_obj.get('message', '').lower()
                        error_reason = ''
                        if error_obj.get('errors'):
                            error_reason = error_obj['errors'][0].get('reason', '').lower()
                        
                        # Log detalhado do erro
                        logger.warning(f"⚠️ 403 Error - Message: '{error_msg}' | Reason: '{error_reason}'")
                        
                        # 🔴 QUOTA EXCEEDED (diária esgotada) - MARCA COMO MORTA
                        if 'quota' in error_msg or 'quota' in error_reason or 'dailylimit' in error_reason:
                            logger.error(f"🚨 QUOTA EXCEEDED on key {self.current_key_index + 1}")
                            self.mark_key_as_exhausted()
                            
                            # Tenta com próxima chave
                            if retry_count < self.max_retries and not self.all_keys_exhausted():
                                logger.info(f"♻️ Tentando com próxima chave disponível...")
                                return await self.make_api_request(url, params, canal_name, retry_count + 1)
                            return None
                        
                        # 🟡 RATE LIMIT (temporário) - AGUARDA E TENTA DE NOVO
                        elif 'ratelimit' in error_msg or 'ratelimit' in error_reason or 'usageratelimit' in error_reason:
                            if retry_count < self.max_retries:
                                wait_time = (2 ** retry_count) * 30  # 30s, 60s, 120s
                                logger.warning(f"⏱️ RATE LIMIT hit on key {self.current_key_index + 1}")
                                logger.info(f"♻️ Retry {retry_count + 1}/{self.max_retries} após {wait_time}s")
                                await asyncio.sleep(wait_time)
                                return await self.make_api_request(url, params, canal_name, retry_count + 1)
                            else:
                                logger.error(f"❌ Max retries atingido após rate limit")
                                return None
                        
                        # 🟠 403 GENÉRICO (sem especificar) - AGUARDA E TENTA DE NOVO
                        else:
                            logger.warning(f"⚠️ 403 genérico (não quota/rate): {error_msg}")
                            
                            # NÃO MARCA COMO EXHAUSTED! Tenta de novo com backoff
                            if retry_count < self.max_retries:
                                wait_time = (2 ** retry_count) * 15  # 15s, 30s, 60s
                                logger.info(f"♻️ Tentando novamente após {wait_time}s (retry {retry_count + 1}/{self.max_retries})")
                                await asyncio.sleep(wait_time)
                                return await self.make_api_request(url, params, canal_name, retry_count + 1)
                            else:
                                # Só depois de 3 tentativas falhas, ENTÃO considera problema
                                logger.warning(f"⚠️ 403 persistente após {self.max_retries} tentativas - pulando requisição")
                                return None
                    
                    # ⚠️ OUTROS ERROS HTTP
                    else:
                        logger.warning(f"⚠️ HTTP {response.status}: {await response.text()}")
                        return None
                        
        except asyncio.TimeoutError:
            logger.warning(f"⏱️ Timeout na requisição")
            if retry_count < self.max_retries:
                await asyncio.sleep(5)
                return await self.make_api_request(url, params, canal_name, retry_count + 1)
            return None
            
        except Exception as e:
            logger.error(f"❌ Exception na requisição: {e}")
            return None

    def clean_youtube_url(self, url: str) -> str:
        """Remove extra paths from YouTube URL"""
        url = re.sub(r'/(videos|channel-analytics|about|featured|playlists|community|channels|streams|shorts).*$', '', url)
        return url

    def is_valid_channel_id(self, channel_id: str) -> bool:
        """Check if a string is a valid YouTube channel ID"""
        if not channel_id:
            return False
        return channel_id.startswith('UC') and len(channel_id) == 24

    def extract_channel_identifier(self, url: str) -> tuple[Optional[str], str]:
        """Extract channel identifier from YouTube URL"""
        url = self.clean_youtube_url(url)
        
        channel_id_match = re.search(r'youtube\.com/channel/([a-zA-Z0-9_-]+)', url)
        if channel_id_match:
            channel_id = channel_id_match.group(1)
            if self.is_valid_channel_id(channel_id):
                return (channel_id, 'id')
        
        handle_match = re.search(r'youtube\.com/@([a-zA-Z0-9._-]+)', url)
        if handle_match:
            handle = handle_match.group(1)
            return (handle, 'handle')
        
        custom_match = re.search(r'youtube\.com/c/([a-zA-Z0-9._-]+)', url)
        if custom_match:
            username = custom_match.group(1)
            return (username, 'username')
        
        user_match = re.search(r'youtube\.com/user/([a-zA-Z0-9._-]+)', url)
        if user_match:
            username = user_match.group(1)
            return (username, 'username')
        
        return (None, 'unknown')

    async def get_channel_id_from_handle(self, handle: str, canal_name: str) -> Optional[str]:
        """Convert handle to channel ID"""
        if self.all_keys_exhausted():
            return None
            
        if handle.startswith('@'):
            handle = handle[1:]
        
        # Try forHandle
        url = f"{self.base_url}/channels"
        params = {'part': 'id', 'forHandle': handle}
        
        data = await self.make_api_request(url, params, canal_name)
        if data and data.get('items'):
            return data['items'][0]['id']
        
        # Try forUsername
        params = {'part': 'id', 'forUsername': handle}
        data = await self.make_api_request(url, params, canal_name)
        if data and data.get('items'):
            return data['items'][0]['id']
        
        return None

    async def get_channel_id(self, url: str, canal_name: str) -> Optional[str]:
        """Get channel ID from URL"""
        identifier, id_type = self.extract_channel_identifier(url)
        
        if not identifier:
            return None
        
        if id_type == 'id' and self.is_valid_channel_id(identifier):
            return identifier
        
        if id_type in ['handle', 'username']:
            return await self.get_channel_id_from_handle(identifier, canal_name)
        
        return None

    async def get_channel_info(self, channel_id: str, canal_name: str) -> Optional[Dict[str, Any]]:
        """Get channel info"""
        if not self.is_valid_channel_id(channel_id):
            return None
        
        url = f"{self.base_url}/channels"
        params = {'part': 'statistics,snippet', 'id': channel_id}
        
        data = await self.make_api_request(url, params, canal_name)
        
        if data and data.get('items'):
            channel = data['items'][0]
            stats = channel.get('statistics', {})
            snippet = channel.get('snippet', {})
            
            return {
                'channel_id': channel_id,
                'title': snippet.get('title'),
                'subscriber_count': int(stats.get('subscriberCount', 0)),
                'video_count': int(stats.get('videoCount', 0)),
                'view_count': int(stats.get('viewCount', 0))
            }
        
        return None

    async def get_channel_videos(self, channel_id: str, canal_name: str, days: int = 60) -> List[Dict[str, Any]]:
        """Get channel videos"""
        if not self.is_valid_channel_id(channel_id):
            return []
        
        if self.all_keys_exhausted():
            return []
        
        videos = []
        page_token = None
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=days)
        
        while True:
            if self.all_keys_exhausted():
                break
            
            url = f"{self.base_url}/search"
            params = {
                'part': 'id,snippet',
                'channelId': channel_id,
                'type': 'video',
                'order': 'date',
                'maxResults': 50,
                'publishedAfter': cutoff_date.isoformat()
            }
            
            if page_token:
                params['pageToken'] = page_token
            
            data = await self.make_api_request(url, params, canal_name)
            
            if not data or not data.get('items'):
                break
            
            video_ids = [item['id']['videoId'] for item in data['items']]
            video_details = await self.get_video_details(video_ids, canal_name)
            
            for item, details in zip(data['items'], video_details):
                if details:
                    video_info = {
                        'video_id': item['id']['videoId'],
                        'titulo': decode_html_entities(item['snippet']['title']),
                        'url_video': f"https://www.youtube.com/watch?v={item['id']['videoId']}",
                        'data_publicacao': item['snippet']['publishedAt'],
                        'views_atuais': details.get('view_count', 0),
                        'likes': details.get('like_count', 0),
                        'comentarios': details.get('comment_count', 0),
                        'duracao': details.get('duration_seconds', 0)
                    }
                    videos.append(video_info)
            
            page_token = data.get('nextPageToken')
            if not page_token:
                break
        
        return videos

    async def get_video_details(self, video_ids: List[str], canal_name: str) -> List[Optional[Dict[str, Any]]]:
        """Get video details"""
        if self.all_keys_exhausted():
            return [None] * len(video_ids)
            
        if not video_ids:
            return []
        
        details = []
        
        for i in range(0, len(video_ids), 50):
            if self.all_keys_exhausted():
                details.extend([None] * (len(video_ids) - i))
                break
                
            batch_ids = video_ids[i:i+50]
            
            url = f"{self.base_url}/videos"
            params = {
                'part': 'statistics,contentDetails',
                'id': ','.join(batch_ids)
            }
            
            data = await self.make_api_request(url, params, canal_name)
            
            if data and data.get('items'):
                for item in data['items']:
                    stats = item.get('statistics', {})
                    content = item.get('contentDetails', {})
                    
                    video_detail = {
                        'view_count': int(stats.get('viewCount', 0)),
                        'like_count': int(stats.get('likeCount', 0)),
                        'comment_count': int(stats.get('commentCount', 0)),
                        'duration_seconds': self.parse_duration(content.get('duration', 'PT0S'))
                    }
                    details.append(video_detail)
            else:
                details.extend([None] * len(batch_ids))
        
        return details

    def parse_duration(self, duration_str: str) -> int:
        """Parse YouTube duration format to seconds"""
        try:
            pattern = r'PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?'
            match = re.match(pattern, duration_str)
            
            if match:
                hours = int(match.group(1) or 0)
                minutes = int(match.group(2) or 0)
                seconds = int(match.group(3) or 0)
                return hours * 3600 + minutes * 60 + seconds
        except:
            pass
        
        return 0

    def calculate_views_by_period(self, videos: List[Dict], current_date: datetime) -> Dict[str, int]:
        """Calculate views for different periods"""
        views_60d = views_30d = views_15d = views_7d = 0
        
        if current_date.tzinfo is None:
            current_date = current_date.replace(tzinfo=timezone.utc)
        
        for video in videos:
            try:
                pub_date_str = video['data_publicacao']
                pub_date = datetime.fromisoformat(pub_date_str.replace('Z', '+00:00'))
                
                days_ago = (current_date - pub_date).days
                
                if days_ago <= 60:
                    views_60d += video['views_atuais']
                if days_ago <= 30:
                    views_30d += video['views_atuais']
                if days_ago <= 15:
                    views_15d += video['views_atuais']
                if days_ago <= 7:
                    views_7d += video['views_atuais']
            except Exception as e:
                continue
        
        return {
            'views_60d': views_60d,
            'views_30d': views_30d,
            'views_15d': views_15d,
            'views_7d': views_7d
        }

    async def get_canal_data(self, url_canal: str, canal_name: str) -> Optional[Dict[str, Any]]:
        """Get complete canal data"""
        try:
            if self.is_canal_failed(url_canal):
                logger.warning(f"⏭️ Skipping {canal_name} - already failed")
                return None
            
            if self.all_keys_exhausted():
                return None
            
            # Rotaciona para próxima chave antes de começar (round-robin)
            self.rotate_to_next_key()
            
            channel_id = await self.get_channel_id(url_canal, canal_name)
            
            if not channel_id:
                self.mark_canal_as_failed(url_canal)
                return None
            
            channel_info = await self.get_channel_info(channel_id, canal_name)
            if not channel_info:
                self.mark_canal_as_failed(url_canal)
                return None
            
            videos = await self.get_channel_videos(channel_id, canal_name, days=60)
            
            current_date = datetime.now(timezone.utc)
            views_by_period = self.calculate_views_by_period(videos, current_date)
            
            videos_7d = sum(1 for v in videos if (current_date - datetime.fromisoformat(v['data_publicacao'].replace('Z', '+00:00'))).days <= 7)
            
            total_engagement = sum(v['likes'] + v['comentarios'] for v in videos)
            total_views = sum(v['views_atuais'] for v in videos)
            engagement_rate = (total_engagement / total_views * 100) if total_views > 0 else 0
            
            result = {
                'inscritos': channel_info['subscriber_count'],
                'videos_publicados_7d': videos_7d,
                'engagement_rate': round(engagement_rate, 2),
                **views_by_period
            }
            
            return result
        
        except Exception as e:
            logger.error(f"❌ Error for {canal_name}: {e}")
            self.mark_canal_as_failed(url_canal)
            return None

    async def get_videos_data(self, url_canal: str, canal_name: str) -> Optional[List[Dict[str, Any]]]:
        """Get videos data for a canal"""
        try:
            if self.is_canal_failed(url_canal):
                return None
            
            if self.all_keys_exhausted():
                return None
            
            channel_id = await self.get_channel_id(url_canal, canal_name)
            
            if not channel_id:
                return None
            
            videos = await self.get_channel_videos(channel_id, canal_name, days=60)
            return videos
        
        except Exception as e:
            logger.error(f"❌ Error getting videos for {canal_name}: {e}")
            return None
