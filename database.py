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
        """Get canais that need data collection (new or >3 days old)"""
        try:
            # Calculate 3 days ago
            three_days_ago = (datetime.now() - timedelta(days=3)).isoformat()
            
            response = self.supabase.table("canais_monitorados").select("*").or_(
                f"ultima_coleta.is.null,ultima_coleta.lt.{three_days_ago}"
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
                "views_60d": data.get("views_60d"),
                "views_30d": data.get("views_30d"),
                "views_15d": data.get("views_15d"),
                "views_7d": data.get("views_7d"),
                "inscritos": data.get("inscritos"),
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
            videos_data = []
            current_date = datetime.now().date().isoformat()
            
            for video in videos:
                video_data = {
                    "canal_id": canal_id,
                    "video_id": video.get("video_id"),
                    "titulo": video.get("titulo"),
                    "url_video": video.get("url_video"),
                    "data_publicacao": video.get("data_publicacao"),
                    "data_coleta": current_date,
                    "views_atuais": video.get("views_atuais"),
                    "likes": video.get("likes"),
                    "comentarios": video.get("comentarios"),
                    "duracao": video.get("duracao")
                }
                videos_data.append(video_data)
            
            if videos_data:
                response = self.supabase.table("videos_historico").upsert(videos_data).execute()
                logger.info(f"Saved {len(videos_data)} videos for canal_id {canal_id}")
                return response.data
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
            query = self.supabase.table("canais_com_metricas").select("*")
            
            # Apply filters
            if nicho:
                query = query.eq("nicho", nicho)
            if subnicho:
                query = query.eq("subnicho", subnicho)
            if views_60d_min:
                query = query.gte("views_60d", views_60d_min)
            if views_30d_min:
                query = query.gte("views_30d", views_30d_min)
            if views_15d_min:
                query = query.gte("views_15d", views_15d_min)
            if views_7d_min:
                query = query.gte("views_7d", views_7d_min)
            if score_min:
                query = query.gte("score_calculado", score_min)
            if growth_min:
                query = query.gte("growth_7d", growth_min)
            
            # Order by score (best first)
            query = query.order("score_calculado", desc=True)
            query = query.range(offset, offset + limit - 1)
            
            response = query.execute()
            return response.data
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
            
            # Join videos with canais to get nicho/subnicho
            query = self.supabase.table("videos_historico").select("""
                *,
                canais_monitorados!inner(nome_canal, nicho, subnicho)
            """).gte("data_publicacao", cutoff_date)
            
            # Apply filters
            if nicho:
                query = query.eq("canais_monitorados.nicho", nicho)
            if subnicho:
                query = query.eq("canais_monitorados.subnicho", subnicho)
            if canal:
                query = query.eq("canais_monitorados.nome_canal", canal)
            if views_min:
                query = query.gte("views_atuais", views_min)
            if growth_min:
                # Growth calculation would need to be done in the view or with subquery
                pass
            
            # Order by specified column
            desc = order_by in ["views_atuais", "growth_video"]
            query = query.order(order_by, desc=desc)
            query = query.range(offset, offset + limit - 1)
            
            response = query.execute()
            
            # Flatten the nested structure
            videos = []
            for item in response.data:
                video = dict(item)
                canal_info = video.pop("canais_monitorados")
                video.update({
                    "nome_canal": canal_info["nome_canal"],
                    "nicho": canal_info["nicho"],
                    "subnicho": canal_info["subnicho"]
                })
                videos.append(video)
            
            return videos
        except Exception as e:
            logger.error(f"Error fetching videos with filters: {e}")
            raise

    async def get_filter_options(self) -> Dict[str, List]:
        """Get available filter options"""
        try:
            # Get unique nichos
            nichos_response = self.supabase.table("canais_monitorados").select("nicho").execute()
            nichos = list(set(item["nicho"] for item in nichos_response.data if item["nicho"]))
            
            # Get unique subnichos
            subnichos_response = self.supabase.table("canais_monitorados").select("subnicho").execute()
            subnichos = list(set(item["subnicho"] for item in subnichos_response.data if item["subnicho"]))
            
            # Get canal names
            canais_response = self.supabase.table("canais_monitorados").select("nome_canal").eq("status", "ativo").execute()
            canais = [item["nome_canal"] for item in canais_response.data]
            
            return {
                "nichos": sorted(nichos),
                "subnichos": sorted(subnichos),
                "canais": sorted(canais)
            }
        except Exception as e:
            logger.error(f"Error fetching filter options: {e}")
            raise

    async def get_system_stats(self) -> Dict[str, Any]:
        """Get system statistics"""
        try:
            # Count canais
            canais_response = self.supabase.table("canais_monitorados").select("id", count="exact").execute()
            total_canais = canais_response.count
            
            # Count videos
            videos_response = self.supabase.table("videos_historico").select("id", count="exact").execute()
            total_videos = videos_response.count
            
            # Last collection info
            last_collection_response = self.supabase.table("canais_monitorados").select("ultima_coleta").order("ultima_coleta", desc=True).limit(1).execute()
            last_collection = last_collection_response.data[0]["ultima_coleta"] if last_collection_response.data else None
            
            return {
                "total_canais": total_canais,
                "total_videos": total_videos,
                "last_collection": last_collection,
                "system_status": "healthy"
            }
        except Exception as e:
            logger.error(f"Error fetching system stats: {e}")
            raise

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
            raise
