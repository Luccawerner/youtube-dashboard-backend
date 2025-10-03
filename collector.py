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
            os.environ.get("YOUTUBE_API_KEY_2")
        ]
        
        # Remove None values
        self.api_keys = [key for key in self.api_keys if key]
        
        if not self.api_keys:
            raise ValueError("At least one YouTube API key is required")
        
        self.current_key_index = 0
        self.base_url = "https://www.googleapis.com/youtube/v3"
        logger.info(f"YouTube collector initialized with {len(self.api_keys)} API keys")

    def get_current_api_key(self) -> str:
        """Get current API key with rotation"""
        return self.api_keys[self.current_key_index]

    def rotate_api_key(self):
        """Rotate to next API key"""
        self.current_key_index = (self.current_key_index + 1) % len(self.api_keys)
        logger.info(f"Rotated to API key {self.current_key_index + 1}")

    def extract_channel_id(self, url: str) -> Optional[str]:
        """Extract channel ID from YouTube URL"""
        patterns = [
            r'youtube\.com/channel/([a-zA-Z0-9_-]+)',
            r'youtube\.com/c/([a-zA-Z0-9_-]+)',
            r'youtube\.com/@([a-zA-Z0-9_-]+)',
            r'youtube\.com/user/([a-zA-Z0-9_-]+)'
        ]
        
        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                return match.group(1)
        
        return None

    async def get_channel_id_from_username(self, username: str) -> Optional[str]:
        """Get channel ID from username/handle"""
        try:
            async with aiohttp.ClientSession() as session:
                # Try with @ handle first
                if username.startswith('@'):
                    username = username[1:]
                
                url = f"{self.base_url}/channels"
                params = {
                    'part': 'id',
                    'forHandle': username,
                    'key': self.get_current_api_key()
                }
                
                async with session.get(url, params=params) as response:
                    if response.status == 200:
                        data = await response.json()
                        if data.get('items'):
                            return data['items'][0]['id']
                    
                    # If handle doesn't work, try forUsername
                    params = {
                        'part': 'id',
                        'forUsername': username,
                        'key': self.get_current_api_key()
                    }
                    
                    async with session.get(url, params=params) as response:
                        if response.status == 200:
                            data = await response.json()
                            if data.get('items'):
                                return data['items'][0]['id']
                        
                        elif response.status == 403:
                            # Quota exceeded, try next key
                            self.rotate_api_key()
                            return await self.get_channel_id_from_username(username)
        
        except Exception as e:
            logger.error(f"Error getting channel ID for {username}: {e}")
        
        return None

    async def get_channel_info(self, channel_id: str) -> Optional[Dict[str, Any]]:
        """Get basic channel information"""
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
                    
                    elif response.status == 403:
                        # Quota exceeded
                        self.rotate_api_key()
                        return await self.get_channel_info(channel_id)
                    
                    else:
                        logger.error(f"Error getting channel info: {response.status}")
        
        except Exception as e:
            logger.error(f"Error getting channel info for {channel_id}: {e}")
        
        return None

    async def get_channel_videos(self, channel_id: str, days: int = 60) -> List[Dict[str, Any]]:
        """Get videos from a channel within specified days"""
        try:
            videos = []
            page_token = None
            cutoff_date = datetime.now(timezone.utc) - timedelta(days=days)
            
            async with aiohttp.ClientSession() as session:
                while True:
                    # Get video IDs from channel
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
                            
                            # Get video details
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
                                    logger.debug(f"Added video: {video_info['titulo']} - Published: {video_info['data_publicacao']}")
                            
                            page_token = data.get('nextPageToken')
                            if not page_token:
                                break
                            
                            # Small delay to avoid rate limiting
                            await asyncio.sleep(0.1)
                        
                        elif response.status == 403:
                            # Quota exceeded
                            self.rotate_api_key()
                            continue
                        
                        else:
                            logger.error(f"Error getting videos: {response.status}")
                            break
            
            logger.info(f"Retrieved {len(videos)} videos for channel {channel_id}")
            return videos
        
        except Exception as e:
            logger.error(f"Error getting videos for channel {channel_id}: {e}")
            return []

    async def get_video_details(self, video_ids: List[str]) -> List[Optional[Dict[str, Any]]]:
        """Get detailed video statistics"""
        try:
            if not video_ids:
                return []
            
            details = []
            
            # Process in batches of 50 (API limit)
            for i in range(0, len(video_ids), 50):
                batch_ids = video_ids[i:i+50]
                
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
                        
                        elif response.status == 403:
                            # Quota exceeded
                            self.rotate_api_key()
                            return await self.get_video_details(video_ids)
                        
                        else:
                            # Add None for failed requests
                            details.extend([None] * len(batch_ids))
                
                # Small delay between batches
                await asyncio.sleep(0.1)
            
            return details
        
        except Exception as e:
            logger.error(f"Error getting video details: {e}")
            return [None] * len(video_ids)

    def parse_duration(self, duration_str: str) -> int:
        """Parse YouTube duration format to seconds"""
        try:
            # Parse ISO 8601 duration (PT1H2M3S)
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
        
        # Ensure current_date has timezone
        if current_date.tzinfo is None:
            current_date = current_date.replace(tzinfo=timezone.utc)
        
        for video in videos:
            try:
                # Parse the date string from YouTube API
                pub_date_str = video['data_publicacao']
                # YouTube API returns ISO format with Z (UTC)
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
            # Extract channel ID
            channel_id = self.extract_channel_id(url_canal)
            
            if not channel_id:
                # Try to get ID from username/handle
                username = url_canal.split('/')[-1]
                channel_id = await self.get_channel_id_from_username(username)
            
            if not channel_id:
                logger.error(f"Could not extract channel ID from URL: {url_canal}")
                return None
            
            # Get channel info
            channel_info = await self.get_channel_info(channel_id)
            if not channel_info:
                return None
            
            # Get videos from last 60 days
            videos = await self.get_channel_videos(channel_id, days=60)
            
            # Calculate views by period - use timezone-aware datetime
            current_date = datetime.now(timezone.utc)
            views_by_period = self.calculate_views_by_period(videos, current_date)
            
            # Count videos published in last 7 days
            videos_7d = 0
            for v in videos:
                try:
                    pub_date = datetime.fromisoformat(v['data_publicacao'].replace('Z', '+00:00'))
                    if (current_date - pub_date).days <= 7:
                        videos_7d += 1
                except:
                    continue
            
            # Calculate engagement rate (simplified)
            total_engagement = sum(v['likes'] + v['comentarios'] for v in videos)
            total_views = sum(v['views_atuais'] for v in videos)
            engagement_rate = (total_engagement / total_views * 100) if total_views > 0 else 0
            
            return {
                'inscritos': channel_info['subscriber_count'],
                'videos_publicados_7d': videos_7d,
                'engagement_rate': round(engagement_rate, 2),
                **views_by_period
            }
        
        except Exception as e:
            logger.error(f"Error getting canal data for {url_canal}: {e}")
            return None

    async def get_videos_data(self, url_canal: str) -> Optional[List[Dict[str, Any]]]:
        """Get videos data for a canal"""
        try:
            # Extract channel ID
            channel_id = self.extract_channel_id(url_canal)
            
            if not channel_id:
                # Try to get ID from username/handle
                username = url_canal.split('/')[-1]
                channel_id = await self.get_channel_id_from_username(username)
            
            if not channel_id:
                logger.error(f"Could not extract channel ID from URL: {url_canal}")
                return None
            
            # Get videos from last 60 days
            videos = await self.get_channel_videos(channel_id, days=60)
            return videos
        
        except Exception as e:
            logger.error(f"Error getting videos data for {url_canal}: {e}")
            return None
