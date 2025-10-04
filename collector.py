import os
import re
import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Optional, Any
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
        
        # Remove None values
        self.api_keys = [key for key in self.api_keys if key]
        
        if not self.api_keys:
            raise ValueError("At least one YouTube API key is required")
        
        self.current_key_index = 0
        self.base_url = "https://www.googleapis.com/youtube/v3"
        self.max_retries = 3
        logger.info(f"YouTube collector initialized with {len(self.api_keys)} API keys")

    def get_current_api_key(self) -> str:
        """Get current API key with rotation"""
        return self.api_keys[self.current_key_index]

    def rotate_api_key(self):
        """Rotate to next API key"""
        self.current_key_index = (self.current_key_index + 1) % len(self.api_keys)
        logger.info(f"Rotated to API key {self.current_key_index + 1}")

    def clean_youtube_url(self, url: str) -> str:
        """Remove extra paths from YouTube URL"""
        url = re.sub(r'/(videos|channel-analytics|about|featured|playlists|community|channels|streams|shorts).*$', '', url)
        return url

    def is_valid_channel_id(self, channel_id: str) -> bool:
        """Check if a string is a valid YouTube channel ID (starts with UC and is 24 chars)"""
        if not channel_id:
            return False
        # YouTube channel IDs start with UC and are typically 24 characters
        return channel_id.startswith('UC') and len(channel_id) == 24

    def extract_channel_identifier(self, url: str) -> tuple[Optional[str], str]:
        """
        Extract channel identifier from YouTube URL
        Returns: (identifier, type) where type is 'id', 'handle', 'username', or 'unknown'
        
        UPDATED: Now supports handles with dots, like @HER.VOICES
        """
        url = self.clean_youtube_url(url)
        
        # Try to match channel ID (UC...)
        channel_id_match = re.search(r'youtube\.com/channel/([a-zA-Z0-9_-]+)', url)
        if channel_id_match:
            channel_id = channel_id_match.group(1)
            if self.is_valid_channel_id(channel_id):
                logger.info(f"Found valid channel ID: {channel_id}")
                return (channel_id, 'id')
        
        # Try to match handle (@username) - UPDATED REGEX TO INCLUDE DOTS
        # Changed from [a-zA-Z0-9_-]+ to [a-zA-Z0-9._-]+ to include dots
        handle_match = re.search(r'youtube\.com/@([a-zA-Z0-9._-]+)', url)
        if handle_match:
            handle = handle_match.group(1)
            logger.info(f"Found handle: @{handle}")
            return (handle, 'handle')
        
        # Try to match custom URL (/c/username) - ALSO UPDATED
        custom_match = re.search(r'youtube\.com/c/([a-zA-Z0-9._-]+)', url)
        if custom_match:
            username = custom_match.group(1)
            logger.info(f"Found custom URL: {username}")
            return (username, 'username')
        
        # Try to match user URL (/user/username) - ALSO UPDATED
        user_match = re.search(r'youtube\.com/user/([a-zA-Z0-9._-]+)', url)
        if user_match:
            username = user_match.group(1)
            logger.info(f"Found user URL: {username}")
            return (username, 'username')
        
        logger.warning(f"Could not extract identifier from URL: {url}")
        return (None, 'unknown')

    async def get_channel_id_from_handle(self, handle: str) -> Optional[str]:
        """Convert a handle (@username) to a proper channel ID (UC...)"""
        retry_count = 0
        
        # Remove @ if present
        if handle.startswith('@'):
            handle = handle[1:]
        
        logger.info(f"Attempting to convert handle '{handle}' to channel ID...")
        
        while retry_count < self.max_retries:
            try:
                async with aiohttp.ClientSession() as session:
                    # Try with forHandle parameter
                    url = f"{self.base_url}/channels"
                    params = {
                        'part': 'id',
                        'forHandle': handle,
                        'key': self.get_current_api_key()
                    }
                    
                    async with session.get(url, params=params) as response:
                        if response.status == 200:
                            data = await response.json()
                            if data.get('items') and len(data['items']) > 0:
                                channel_id = data['items'][0]['id']
                                logger.info(f"✅ Successfully converted handle '{handle}' to channel ID: {channel_id}")
                                return channel_id
                        elif response.status == 403:
                            retry_count += 1
                            if retry_count < self.max_retries:
                                logger.warning(f"API key quota exceeded, rotating to next key...")
                                self.rotate_api_key()
                                await asyncio.sleep(1)
                                continue
                        
                        # If forHandle didn't work, try forUsername
                        logger.info(f"forHandle failed, trying forUsername for '{handle}'...")
                        params = {
                            'part': 'id',
                            'forUsername': handle,
                            'key': self.get_current_api_key()
                        }
                        
                        async with session.get(url, params=params) as response2:
                            if response2.status == 200:
                                data = await response2.json()
                                if data.get('items') and len(data['items']) > 0:
                                    channel_id = data['items'][0]['id']
                                    logger.info(f"✅ Successfully converted username '{handle}' to channel ID: {channel_id}")
                                    return channel_id
                            elif response2.status == 403:
                                retry_count += 1
                                if retry_count < self.max_retries:
                                    logger.warning(f"API key quota exceeded, rotating to next key...")
                                    self.rotate_api_key()
                                    await asyncio.sleep(1)
                                    continue
                        
                        logger.error(f"❌ Could not convert handle/username '{handle}' to channel ID (both methods failed)")
                        return None
            
            except Exception as e:
                logger.error(f"Error converting handle '{handle}' to channel ID: {e}")
                retry_count += 1
                if retry_count < self.max_retries:
                    await asyncio.sleep(1)
                else:
                    return None
        
        return None

    async def get_channel_id(self, url: str) -> Optional[str]:
        """
        Get a valid channel ID from any YouTube URL
        This is the main function that handles all URL types
        """
        identifier, id_type = self.extract_channel_identifier(url)
        
        if not identifier:
            logger.error(f"❌ Could not extract any identifier from URL: {url}")
            return None
        
        # If it's already a valid ID, return it
        if id_type == 'id' and self.is_valid_channel_id(identifier):
            logger.info(f"✅ Already have valid channel ID: {identifier}")
            return identifier
        
        # If it's a handle or username, convert it to ID
        if id_type in ['handle', 'username']:
            logger.info(f"🔄 Need to convert {id_type} '{identifier}' to channel ID...")
            channel_id = await self.get_channel_id_from_handle(identifier)
            if channel_id:
                logger.info(f"✅ Conversion successful: {identifier} → {channel_id}")
                return channel_id
            else:
                logger.error(f"❌ Failed to convert {id_type} '{identifier}' to channel ID")
                return None
        
        logger.error(f"❌ Unknown identifier type: {id_type}")
        return None

    async def get_channel_info(self, channel_id: str) -> Optional[Dict[str, Any]]:
        """Get basic channel information with retry limit"""
        if not self.is_valid_channel_id(channel_id):
            logger.error(f"❌ Invalid channel ID format: {channel_id}")
            return None
        
        retry_count = 0
        
        while retry_count < self.max_retries:
            try:
                async with aiohttp.ClientSession() as session:
                    url = f"{self.base_url}/channels"
                    params = {
                        'part': 'statistics,snippet',
                        'id': channel_id,
                        'key': self.get_current_api_key()
                    }
                    
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
                            else:
                                return None
                        
                        elif response.status == 403:
                            retry_count += 1
                            if retry_count < self.max_retries:
                                self.rotate_api_key()
                                await asyncio.sleep(1)
                                continue
                            else:
                                logger.error(f"Max retries reached for channel {channel_id}")
                                return None
                        else:
                            logger.error(f"Error getting channel info: {response.status}")
                            return None
            
            except Exception as e:
                logger.error(f"Error getting channel info for {channel_id}: {e}")
                return None
        
        return None

    async def get_channel_videos(self, channel_id: str, days: int = 60) -> List[Dict[str, Any]]:
        """Get videos from a channel within specified days with retry limit"""
        if not self.is_valid_channel_id(channel_id):
            logger.error(f"❌ Invalid channel ID format for get_channel_videos: {channel_id}")
            return []
        
        try:
            videos = []
            page_token = None
            cutoff_date = datetime.now(timezone.utc) - timedelta(days=days)
            retry_count = 0
            
            async with aiohttp.ClientSession() as session:
                while True:
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
                    
                    logger.info(f"Fetching videos for channel {channel_id} since {cutoff_date.isoformat()}")
                    
                    async with session.get(url, params=params) as response:
                        if response.status == 200:
                            data = await response.json()
                            
                            if not data.get('items'):
                                break
                            
                            video_ids = [item['id']['videoId'] for item in data['items']]
                            video_details = await self.get_video_details(video_ids)
                            
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
                            
                            retry_count = 0
                            await asyncio.sleep(0.1)
                        
                        elif response.status == 403:
                            retry_count += 1
                            if retry_count < self.max_retries:
                                self.rotate_api_key()
                                await asyncio.sleep(2)
                                continue
                            else:
                                logger.error(f"Max retries reached for channel {channel_id}")
                                break
                        
                        else:
                            error_text = await response.text()
                            logger.error(f"Error getting videos (status {response.status}): {error_text}")
                            break
            
            logger.info(f"Retrieved {len(videos)} videos for channel {channel_id}")
            return videos
        
        except Exception as e:
            logger.error(f"Error getting videos for channel {channel_id}: {e}")
            return []

    async def get_video_details(self, video_ids: List[str]) -> List[Optional[Dict[str, Any]]]:
        """Get detailed video statistics with retry limit"""
        try:
            if not video_ids:
                return []
            
            details = []
            
            for i in range(0, len(video_ids), 50):
                batch_ids = video_ids[i:i+50]
                retry_count = 0
                
                while retry_count < self.max_retries:
                    async with aiohttp.ClientSession() as session:
                        url = f"{self.base_url}/videos"
                        params = {
                            'part': 'statistics,contentDetails',
                            'id': ','.join(batch_ids),
                            'key': self.get_current_api_key()
                        }
                        
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
                                break
                            
                            elif response.status == 403:
                                retry_count += 1
                                if retry_count < self.max_retries:
                                    self.rotate_api_key()
                                    await asyncio.sleep(1)
                                    continue
                                else:
                                    logger.error(f"Max retries reached for video details")
                                    details.extend([None] * len(batch_ids))
                                    break
                            
                            else:
                                details.extend([None] * len(batch_ids))
                                break
                
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
                logger.error(f"Error calculating views for video: {e}")
                continue
        
        return {
            'views_60d': views_60d,
            'views_30d': views_30d,
            'views_15d': views_15d,
            'views_7d': views_7d
        }

    async def get_canal_data(self, url_canal: str) -> Optional[Dict[str, Any]]:
        """Get complete canal data"""
        try:
            logger.info(f"🔍 Starting collection for URL: {url_canal}")
            
            # Get proper channel ID from URL
            channel_id = await self.get_channel_id(url_canal)
            
            if not channel_id:
                logger.error(f"❌ Could not get channel ID from URL: {url_canal}")
                return None
            
            logger.info(f"✅ Using channel ID: {channel_id}")
            
            channel_info = await self.get_channel_info(channel_id)
            if not channel_info:
                logger.error(f"❌ Could not get channel info for {channel_id}")
                return None
            
            videos = await self.get_channel_videos(channel_id, days=60)
            
            current_date = datetime.now(timezone.utc)
            views_by_period = self.calculate_views_by_period(videos, current_date)
            
            videos_7d = 0
            for v in videos:
                try:
                    pub_date = datetime.fromisoformat(v['data_publicacao'].replace('Z', '+00:00'))
                    if (current_date - pub_date).days <= 7:
                        videos_7d += 1
                except:
                    continue
            
            total_engagement = sum(v['likes'] + v['comentarios'] for v in videos)
            total_views = sum(v['views_atuais'] for v in videos)
            engagement_rate = (total_engagement / total_views * 100) if total_views > 0 else 0
            
            result = {
                'inscritos': channel_info['subscriber_count'],
                'videos_publicados_7d': videos_7d,
                'engagement_rate': round(engagement_rate, 2),
                **views_by_period
            }
            
            logger.info(f"✅ Successfully collected data for channel {channel_id}: {result}")
            return result
        
        except Exception as e:
            logger.error(f"❌ Error getting canal data for {url_canal}: {e}")
            return None

    async def get_videos_data(self, url_canal: str) -> Optional[List[Dict[str, Any]]]:
        """Get videos data for a canal"""
        try:
            logger.info(f"🔍 Getting videos for URL: {url_canal}")
            
            # Get proper channel ID from URL
            channel_id = await self.get_channel_id(url_canal)
            
            if not channel_id:
                logger.error(f"❌ Could not get channel ID from URL: {url_canal}")
                return None
            
            logger.info(f"✅ Using channel ID: {channel_id}")
            
            videos = await self.get_channel_videos(channel_id, days=60)
            return videos
        
        except Exception as e:
            logger.error(f"❌ Error getting videos data for {url_canal}: {e}")
            return None
