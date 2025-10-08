import os
import re
import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Optional, Any, Set
import aiohttp
import json

logger = logging.getLogger(__name__)

class YouTubeCollector:
    def __init__(self):
        self.api_keys = [
            os.environ.get("YOUTUBE_API_KEY_1"),
            os.environ.get("YOUTUBE_API_KEY_2"),
            os.environ.get("YOUTUBE_API_KEY_3"),
            os.environ.get("YOUTUBE_API_KEY_4"),
            os.environ.get("YOUTUBE_API_KEY_5"),
            os.environ.get("YOUTUBE_API_KEY_6")
        ]
        
        self.api_keys = [key for key in self.api_keys if key]
        
        if not self.api_keys:
            raise ValueError("At least one YouTube API key is required")
        
        self.current_key_index = 0
        self.exhausted_keys = set()
        self.base_url = "https://www.googleapis.com/youtube/v3"
        self.max_retries = 1  # ONLY 1 retry per key
        
        # REQUEST COUNTER
        self.total_requests = 0
        self.requests_per_canal: Dict[str, int] = {}
        self.failed_canals: Set[str] = set()
        
        logger.info(f"YouTube collector initialized with {len(self.api_keys)} API keys")

    def reset_for_new_collection(self):
        """Reset collector state before starting a new collection"""
        self.exhausted_keys = set()
        self.failed_canals = set()
        self.total_requests = 0
        self.requests_per_canal = {}
        self.current_key_index = 0
        logger.info("=" * 80)
        logger.info("🔄 COLLECTOR RESET")
        logger.info(f"✅ All {len(self.api_keys)} API keys refreshed")
        logger.info("✅ Failed canals list cleared")
        logger.info("✅ Request counters reset to zero")
        logger.info("=" * 80)

    def increment_request_counter(self, canal_name: str = "system"):
        """Increment request counter"""
        self.total_requests += 1
        if canal_name not in self.requests_per_canal:
            self.requests_per_canal[canal_name] = 0
        self.requests_per_canal[canal_name] += 1
        
    def get_request_stats(self) -> Dict[str, Any]:
        """Get request statistics"""
        return {
            "total_requests": self.total_requests,
            "requests_per_canal": self.requests_per_canal.copy(),
            "failed_canals": list(self.failed_canals),
            "exhausted_keys": len(self.exhausted_keys),
            "active_keys": len(self.api_keys) - len(self.exhausted_keys)
        }

    def get_current_api_key(self) -> str:
        """Get current API key with rotation"""
        return self.api_keys[self.current_key_index]

    def rotate_api_key(self):
        """Rotate to next API key"""
        self.exhausted_keys.add(self.current_key_index)
        self.current_key_index = (self.current_key_index + 1) % len(self.api_keys)
        logger.warning(f"⚠️ API key exhausted. Rotated to key {self.current_key_index + 1}")
    
    def all_keys_exhausted(self) -> bool:
        """Check if all API keys are exhausted"""
        return len(self.exhausted_keys) >= len(self.api_keys)

    def mark_canal_as_failed(self, canal_url: str):
        """Mark a canal as failed to avoid retrying with other keys"""
        self.failed_canals.add(canal_url)

    def is_canal_failed(self, canal_url: str) -> bool:
        """Check if canal already failed"""
        return canal_url in self.failed_canals
    
    def is_quota_error(self, error_data: dict) -> bool:
        """
        🆕 NOVA FUNÇÃO: Verifica se o erro 403 é REALMENTE de quota esgotada
        
        Retorna True apenas se for erro de quota real
        Retorna False se for outro tipo de erro 403 (canal privado, deletado, etc)
        """
        try:
            error_obj = error_data.get('error', {})
            message = error_obj.get('message', '').lower()
            
            # Lista de palavras-chave que indicam quota esgotada
            quota_keywords = [
                'quota',
                'quotaexceeded',
                'dailylimitexceeded',
                'usageratelimitexceeded',
                'ratelimitexceeded'
            ]
            
            # Verifica se alguma palavra-chave está na mensagem
            is_quota = any(keyword in message for keyword in quota_keywords)
            
            if is_quota:
                logger.error(f"🚨 REAL QUOTA ERROR: {message}")
            else:
                logger.warning(f"⚠️ 403 error but NOT quota: {message}")
            
            return is_quota
            
        except Exception as e:
            logger.error(f"Error checking quota error: {e}")
            # Em caso de dúvida, assume que NÃO é quota (mais seguro)
            return False

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
        """Convert handle to channel ID - ONLY 1 RETRY"""
        if self.all_keys_exhausted():
            return None
            
        if handle.startswith('@'):
            handle = handle[1:]
        
        try:
            async with aiohttp.ClientSession() as session:
                url = f"{self.base_url}/channels"
                params = {
                    'part': 'id',
                    'forHandle': handle,
                    'key': self.get_current_api_key()
                }
                
                self.increment_request_counter(canal_name)
                
                async with session.get(url, params=params) as response:
                    if response.status == 200:
                        data = await response.json()
                        if data.get('items'):
                            return data['items'][0]['id']
                    elif response.status == 403:
                        error_data = await response.json()
                        if self.is_quota_error(error_data):
                            self.rotate_api_key()
                        return None
                
                # Try forUsername
                params['forUsername'] = handle
                del params['forHandle']
                
                self.increment_request_counter(canal_name)
                
                async with session.get(url, params=params) as response2:
                    if response2.status == 200:
                        data = await response2.json()
                        if data.get('items'):
                            return data['items'][0]['id']
                    elif response2.status == 403:
                        error_data = await response2.json()
                        if self.is_quota_error(error_data):
                            self.rotate_api_key()
                
                return None
        
        except Exception as e:
            logger.error(f"Error converting handle: {e}")
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
        """Get channel info - ONLY 1 RETRY - 🆕 CORRIGIDO"""
        if not self.is_valid_channel_id(channel_id):
            return None
        
        if self.all_keys_exhausted():
            return None
        
        try:
            async with aiohttp.ClientSession() as session:
                url = f"{self.base_url}/channels"
                params = {
                    'part': 'statistics,snippet',
                    'id': channel_id,
                    'key': self.get_current_api_key()
                }
                
                self.increment_request_counter(canal_name)
                
                async with session.get(url, params=params) as response:
                    if response.status == 200:
                        data = await response.json()
                        if data.get('items'):
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
                    
                    elif response.status == 403:
                        error_data = await response.json()
                        # 🆕 VERIFICAÇÃO INTELIGENTE
                        if self.is_quota_error(error_data):
                            self.rotate_api_key()
                        else:
                            # Não é erro de quota, apenas problema com este canal
                            logger.warning(f"❌ Canal {canal_name} retornou 403 mas NÃO é quota - pulando")
                        return None
                    
                    return None
        
        except Exception as e:
            logger.error(f"Error getting channel info: {e}")
            return None

    async def get_channel_videos(self, channel_id: str, canal_name: str, days: int = 60) -> List[Dict[str, Any]]:
        """Get channel videos - 🆕 CORRIGIDO"""
        if not self.is_valid_channel_id(channel_id):
            return []
        
        if self.all_keys_exhausted():
            return []
        
        try:
            videos = []
            page_token = None
            cutoff_date = datetime.now(timezone.utc) - timedelta(days=days)
            
            async with aiohttp.ClientSession() as session:
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
                        'publishedAfter': cutoff_date.isoformat(),
                        'key': self.get_current_api_key()
                    }
                    
                    if page_token:
                        params['pageToken'] = page_token
                    
                    self.increment_request_counter(canal_name)
                    
                    async with session.get(url, params=params) as response:
                        if response.status == 200:
                            data = await response.json()
                            
                            if not data.get('items'):
                                break
                            
                            video_ids = [item['id']['videoId'] for item in data['items']]
                            video_details = await self.get_video_details(video_ids, canal_name)
                            
                            for item, details in zip(data['items'], video_details):
                                if details:
                                    video_info = {
                                        'video_id': item['id']['videoId'],
                                        'titulo': item['snippet']['title'],
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
                            
                            await asyncio.sleep(0.1)
                        
                        elif response.status == 403:
                            error_data = await response.json()
                            # 🆕 VERIFICAÇÃO INTELIGENTE
                            if self.is_quota_error(error_data):
                                self.rotate_api_key()
                            else:
                                logger.warning(f"❌ Canal {canal_name} - vídeos retornaram 403 mas NÃO é quota")
                            break
                        
                        else:
                            break
            
            return videos
        
        except Exception as e:
            logger.error(f"Error getting videos: {e}")
            return []

    async def get_video_details(self, video_ids: List[str], canal_name: str) -> List[Optional[Dict[str, Any]]]:
        """Get video details - 🆕 CORRIGIDO"""
        if self.all_keys_exhausted():
            return [None] * len(video_ids)
            
        try:
            if not video_ids:
                return []
            
            details = []
            
            for i in range(0, len(video_ids), 50):
                if self.all_keys_exhausted():
                    details.extend([None] * (len(video_ids) - i))
                    break
                    
                batch_ids = video_ids[i:i+50]
                
                async with aiohttp.ClientSession() as session:
                    url = f"{self.base_url}/videos"
                    params = {
                        'part': 'statistics,contentDetails',
                        'id': ','.join(batch_ids),
                        'key': self.get_current_api_key()
                    }
                    
                    self.increment_request_counter(canal_name)
                    
                    async with session.get(url, params=params) as response:
                        if response.status == 200:
                            data = await response.json()
                            
                            for item in data.get('items', []):
                                stats = item.get('statistics', {})
                                content = item.get('contentDetails', {})
                                
                                video_detail = {
                                    'view_count': int(stats.get('viewCount', 0)),
                                    'like_count': int(stats.get('likeCount', 0)),
                                    'comment_count': int(stats.get('commentCount', 0)),
                                    'duration_seconds': self.parse_duration(content.get('duration', 'PT0S'))
                                }
                                details.append(video_detail)
                        
                        elif response.status == 403:
                            error_data = await response.json()
                            # 🆕 VERIFICAÇÃO INTELIGENTE
                            if self.is_quota_error(error_data):
                                self.rotate_api_key()
                            details.extend([None] * len(batch_ids))
                        
                        else:
                            details.extend([None] * len(batch_ids))
                
                await asyncio.sleep(0.1)
            
            return details
        
        except Exception as e:
            logger.error(f"Error getting video details: {e}")
            return [None] * len(video_ids)

    def parse_duration(self, duration_str: str) -> int:
        """Parse YouTube duration format to seconds"""
        try:
            import re
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
            # Check if canal already failed
            if self.is_canal_failed(url_canal):
                logger.warning(f"Skipping {canal_name} - already failed")
                return None
            
            if self.all_keys_exhausted():
                return None
            
            # Get channel ID
            channel_id = await self.get_channel_id(url_canal, canal_name)
            
            if not channel_id:
                self.mark_canal_as_failed(url_canal)
                return None
            
            # Get channel info
            channel_info = await self.get_channel_info(channel_id, canal_name)
            if not channel_info:
                self.mark_canal_as_failed(url_canal)
                return None
            
            # Get videos
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
            logger.error(f"Error for {canal_name}: {e}")
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
            logger.error(f"Error getting videos for {canal_name}: {e}")
            return None
