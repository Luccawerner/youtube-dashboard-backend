import os
import asyncio
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Any
import logging
from supabase import create_client, Client
import json

logger = logging.getLogger(__name__)

class SupabaseClient:
    def __init__(self):
        url = os.environ.get("SUPABASE_URL")
        key = os.environ.get("SUPABASE_KEY")
        
        if not url or not key:
            raise ValueError("SUPABASE_URL and SUPABASE_KEY environment variables are required")
        
        self.supabase: Client = create_client(url, key)
        logger.info("Supabase client initialized")

    async def test_connection(self):
        """Test database connection"""
        try:
            response = self.supabase.table("canais_monitorados").select("id").limit(1).execute()
            return True
        except Exception as e:
            logger.error(f"Database connection test failed: {e}")
            raise

    async def upsert_canal(self, canal_data: Dict[str, Any]) -> Dict:
        """Insert or update a canal"""
        try:
            response = self.supabase.table("canais_monitorados").upsert({
                "nome_canal": canal_data.get("nome_canal"),
                "url_canal": canal_data.get("url_canal"),
                "nicho": canal_data.get("nicho"),
                "subnicho": canal_data.get("subnicho"),
                "status": canal_data.get("status", "ativo")
            }).execute()
            
            logger.info(f"Canal upserted: {canal_data.get('nome_canal')}")
            return response.data[0] if response.data else None
        except Exception as e:
            logger.error(f"Error upserting canal: {e}")
            raise

    async def get_canais_for_collection(self) -> List[Dict]:
        """Get canais that need data collection"""
        try:
            # Get canais that never had collection or last collection > 1 day ago
            one_day_ago = (datetime.now() - timedelta(days=1)).isoformat()
            
            response = self.supabase.table("canais_monitorados").select("*").or_(
                f"ultima_coleta.is.null,ultima_coleta.lt.{one_day_ago}"
            ).eq("status", "ativo").execute()
            
            logger.info(f"Found {len(response.data)} canais needing collection")
            return response.data
        except Exception as e:
            logger.error(f"Error getting canais for collection: {e}")
            raise

    async def save_canal_data(self, canal_id: int, data: Dict[str, Any]):
        """Save canal metrics data"""
        try:
            canal_data = {
                "canal_id": canal_id,
                "data_coleta": datetime.now().date().isoformat(),
                "views_60d": data.get("views_60d", 0),
                "views_30d": data.get("views_30d", 0),
                "views_15d": data.get("views_15d", 0),
                "views_7d": data.get("views_7d", 0),
                "inscritos": data.get("inscritos", 0),
                "videos_publicados_7d": data.get("videos_publicados_7d", 0),
                "engagement_rate": data.get("engagement_rate", 0.0)
            }
            
            response = self.supabase.table("dados_canais_historico").upsert(canal_data).execute()
            logger.info(f"Canal data saved for canal_id {canal_id}")
            return response.data
        except Exception as e:
            logger.error(f"Error saving canal data: {e}")
            raise

    async def save_videos_data(self, canal_id: int, videos: List[Dict[str, Any]]):
        """Save videos data"""
        try:
            if not videos:
                logger.info(f"No videos to save for canal_id {canal_id}")
                return []
            
            videos_data = []
            current_date = datetime.now().date().isoformat()
            
            for video in videos:
                video_data = {
                    "canal_id": canal_id,
                    "video_id": video.get("video_id"),
                    "titulo": video.get("titulo", "")[:500],  # Limit title length
                    "url_video": video.get("url_video"),
                    "data_publicacao": video.get("data_publicacao"),
                    "data_coleta": current_date,
                    "views_atuais": video.get("views_atuais", 0),
                    "likes": video.get("likes", 0),
                    "comentarios": video.get("comentarios", 0),
                    "duracao": video.get("duracao", 0)
                }
                videos_data.append(video_data)
            
            # Insert in batches of 100 to avoid timeout
            batch_size = 100
            all_responses = []
            
            for i in range(0, len(videos_data), batch_size):
                batch = videos_data[i:i + batch_size]
                response = self.supabase.table("videos_historico").upsert(batch).execute()
                all_responses.extend(response.data)
            
            logger.info(f"Saved {len(videos_data)} videos for canal_id {canal_id}")
            return all_responses
        except Exception as e:
            logger.error(f"Error saving videos data: {e}")
            raise

    async def update_last_collection(self, canal_id: int):
        """Update ultima_coleta timestamp for a canal"""
        try:
            response = self.supabase.table("canais_monitorados").update({
                "ultima_coleta": datetime.now().isoformat()
            }).eq("id", canal_id).execute()
            
            logger.info(f"Updated last collection for canal_id {canal_id}")
            return response.data
        except Exception as e:
            logger.error(f"Error updating last collection: {e}")
            raise

    async def get_canais_with_filters(
        self,
        nicho: Optional[str] = None,
        subnicho: Optional[str] = None,
        views_60d_min: Optional[int] = None,
        views_30d_min: Optional[int] = None,
        views_15d_min: Optional[int] = None,
        views_7d_min: Optional[int] = None,
        score_min: Optional[float] = None,
        growth_min: Optional[float] = None,
        limit: int = 100,
        offset: int = 0
    ) -> List[Dict]:
        """Get canais with filters for Funcionalidade 1"""
        try:
            # Use the view canais_com_metricas
            query = self.supabase.table("canais_com_metricas").select("*")
            
            # Apply filters
            if nicho and nicho != "todos":
                query = query.eq("nicho", nicho)
            if subnicho and subnicho != "todos":
                query = query.eq("subnicho", subnicho)
            if views_60d_min is not None:
                query = query.gte("views_60d", views_60d_min)
            if views_30d_min is not None:
                query = query.gte("views_30d", views_30d_min)
            if views_15d_min is not None:
                query = query.gte("views_15d", views_15d_min)
            if views_7d_min is not None:
                query = query.gte("views_7d", views_7d_min)
            if score_min is not None:
                query = query.gte("score_calculado", score_min)
            if growth_min is not None:
                query = query.gte("growth_7d", growth_min)
            
            # Filter only active canais
            query = query.eq("status", "ativo")
            
            # Order by score (best first), handling nulls
            query = query.order("score_calculado", desc=True, nullsfirst=False)
            
            # Apply pagination
            query = query.range(offset, offset + limit - 1)
            
            response = query.execute()
            
            # Process response data
            canais_data = []
            for canal in response.data:
                # Ensure all fields exist with default values
                processed_canal = {
                    "id": canal.get("id"),
                    "nome_canal": canal.get("nome_canal", ""),
                    "url_canal": canal.get("url_canal", ""),
                    "nicho": canal.get("nicho", ""),
                    "subnicho": canal.get("subnicho", ""),
                    "status": canal.get("status", "ativo"),
                    "views_60d": canal.get("views_60d", 0),
                    "views_30d": canal.get("views_30d", 0),
                    "views_15d": canal.get("views_15d", 0),
                    "views_7d": canal.get("views_7d", 0),
                    "inscritos": canal.get("inscritos", 0),
                    "growth_60d": canal.get("growth_60d", 0),
                    "growth_30d": canal.get("growth_30d", 0),
                    "growth_15d": canal.get("growth_15d", 0),
                    "growth_7d": canal.get("growth_7d", 0),
                    "growth_inscritos": canal.get("growth_inscritos", 0),
                    "score_calculado": canal.get("score_calculado", 0),
                    "ultima_atualizacao": canal.get("ultima_atualizacao")
                }
                canais_data.append(processed_canal)
            
            return canais_data
        except Exception as e:
            logger.error(f"Error fetching canais with filters: {e}")
            raise

    async def get_videos_with_filters(
        self,
        nicho: Optional[str] = None,
        subnicho: Optional[str] = None,
        canal: Optional[str] = None,
        periodo_publicacao: str = "60d",
        views_min: Optional[int] = None,
        growth_min: Optional[float] = None,
        order_by: str = "views_atuais",
        limit: int = 100,
        offset: int = 0
    ) -> List[Dict]:
        """Get videos with filters for Funcionalidade 2"""
        try:
            # Calculate date filter based on periodo_publicacao
            days_map = {"60d": 60, "30d": 30, "15d": 15, "7d": 7}
            days = days_map.get(periodo_publicacao, 60)
            cutoff_date = (datetime.now() - timedelta(days=days)).isoformat()
            
            # Get latest videos with canal information
            query = self.supabase.table("videos_historico").select(
                "*, canais_monitorados!inner(nome_canal, url_canal, nicho, subnicho)"
            ).gte("data_publicacao", cutoff_date)
            
            # Apply filters
            if nicho and nicho != "todos":
                query = query.eq("canais_monitorados.nicho", nicho)
            if subnicho and subnicho != "todos":
                query = query.eq("canais_monitorados.subnicho", subnicho)
            if canal and canal != "todos":
                query = query.eq("canais_monitorados.nome_canal", canal)
            if views_min is not None:
                query = query.gte("views_atuais", views_min)
            
            # Order by specified column
            if order_by == "views_atuais":
                query = query.order("views_atuais", desc=True)
            elif order_by == "data_publicacao":
                query = query.order("data_publicacao", desc=True)
            else:
                query = query.order("views_atuais", desc=True)
            
            # Apply pagination
            query = query.range(offset, offset + limit - 1)
            
            response = query.execute()
            
            # Process and flatten the nested structure
            videos = []
            for item in response.data:
                canal_info = item.pop("canais_monitorados", {})
                
                # Calculate simple growth if we have previous data
                growth_video = 0
                if growth_min is not None:
                    # Skip videos without minimum growth
                    # This would need historical data to calculate properly
                    pass
                
                video = {
                    "id": item.get("id"),
                    "video_id": item.get("video_id"),
                    "titulo": item.get("titulo", ""),
                    "url_video": item.get("url_video", ""),
                    "nome_canal": canal_info.get("nome_canal", ""),
                    "url_canal": canal_info.get("url_canal", ""),
                    "nicho": canal_info.get("nicho", ""),
                    "subnicho": canal_info.get("subnicho", ""),
                    "data_publicacao": item.get("data_publicacao"),
                    "views_atuais": item.get("views_atuais", 0),
                    "likes": item.get("likes", 0),
                    "comentarios": item.get("comentarios", 0),
                    "duracao": item.get("duracao", 0),
                    "growth_video": growth_video,
                    "data_coleta": item.get("data_coleta")
                }
                videos.append(video)
            
            return videos
        except Exception as e:
            logger.error(f"Error fetching videos with filters: {e}")
            raise

    async def get_filter_options(self) -> Dict[str, List]:
        """Get available filter options"""
        try:
            # Get unique nichos
            nichos_response = self.supabase.table("canais_monitorados").select("nicho").eq("status", "ativo").execute()
            nichos = list(set(item["nicho"] for item in nichos_response.data if item.get("nicho")))
            
            # Get unique subnichos
            subnichos_response = self.supabase.table("canais_monitorados").select("subnicho").eq("status", "ativo").execute()
            subnichos = list(set(item["subnicho"] for item in subnichos_response.data if item.get("subnicho")))
            
            # Get canal names
            canais_response = self.supabase.table("canais_monitorados").select("nome_canal").eq("status", "ativo").execute()
            canais = [item["nome_canal"] for item in canais_response.data if item.get("nome_canal")]
            
            return {
                "nichos": sorted([n for n in nichos if n]),
                "subnichos": sorted([s for s in subnichos if s]),
                "canais": sorted([c for c in canais if c])
            }
        except Exception as e:
            logger.error(f"Error fetching filter options: {e}")
            raise

    async def get_system_stats(self) -> Dict[str, Any]:
        """Get system statistics"""
        try:
            # Count canais
            canais_response = self.supabase.table("canais_monitorados").select("id", count="exact").eq("status", "ativo").execute()
            total_canais = canais_response.count or 0
            
            # Count videos (from last 30 days to avoid huge counts)
            thirty_days_ago = (datetime.now() - timedelta(days=30)).isoformat()
            videos_response = self.supabase.table("videos_historico").select("id", count="exact").gte("data_coleta", thirty_days_ago).execute()
            total_videos = videos_response.count or 0
            
            # Last collection info
            last_collection_response = self.supabase.table("canais_monitorados").select("ultima_coleta").order("ultima_coleta", desc=True).limit(1).execute()
            last_collection = last_collection_response.data[0]["ultima_coleta"] if last_collection_response.data else None
            
            return {
                "total_canais": total_canais,
                "total_videos_30d": total_videos,
                "last_collection": last_collection,
                "system_status": "healthy"
            }
        except Exception as e:
            logger.error(f"Error fetching system stats: {e}")
            return {
                "total_canais": 0,
                "total_videos_30d": 0,
                "last_collection": None,
                "system_status": "error"
            }

    async def cleanup_old_data(self):
        """Clean up data older than 60 days"""
        try:
            cutoff_date = (datetime.now() - timedelta(days=60)).date().isoformat()
            
            # Clean old canal data
            canal_response = self.supabase.table("dados_canais_historico").delete().lt("data_coleta", cutoff_date).execute()
            
            # Clean old video data
            video_response = self.supabase.table("videos_historico").delete().lt("data_coleta", cutoff_date).execute()
            
            logger.info(f"Cleaned up old data before {cutoff_date}")
        except Exception as e:
            logger.error(f"Error cleaning up old data: {e}")
            # Don't raise, just log - cleanup is not critical
