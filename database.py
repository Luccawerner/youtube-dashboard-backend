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
                "lingua": canal_data.get("lingua", "English"),
                "tipo": canal_data.get("tipo", "minerado"),
                "status": canal_data.get("status", "ativo")
            }).execute()
            
            logger.info(f"Canal upserted: {canal_data.get('nome_canal')}")
            return response.data[0] if response.data else None
        except Exception as e:
            logger.error(f"Error upserting canal: {e}")
            raise

    async def get_canais_for_collection(self) -> List[Dict]:
        """Get ALL active canais for daily collection"""
        try:
            response = self.supabase.table("canais_monitorados").select("*").eq("status", "ativo").execute()
            
            logger.info(f"Found {len(response.data)} canais needing collection (ALL active canais)")
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
        lingua: Optional[str] = None,
        tipo: Optional[str] = None,
        views_60d_min: Optional[int] = None,
        views_30d_min: Optional[int] = None,
        views_15d_min: Optional[int] = None,
        views_7d_min: Optional[int] = None,
        score_min: Optional[float] = None,
        growth_min: Optional[float] = None,
        limit: int = 100,
        offset: int = 0
    ) -> List[Dict]:
        """Get canais with filters - retorna TODOS os canais, com ou sem métricas"""
        try:
            # Query direta com LEFT JOIN para pegar TODOS os canais
            query = self.supabase.table("canais_monitorados").select("""
                *,
                dados_canais_historico(
                    views_60d, views_30d, views_15d, views_7d,
                    inscritos, engagement_rate, videos_publicados_7d
                )
            """).eq("status", "ativo")
            
            if nicho:
                query = query.eq("nicho", nicho)
            if subnicho:
                query = query.eq("subnicho", subnicho)
            if lingua:
                query = query.eq("lingua", lingua)
            if tipo:
                query = query.eq("tipo", tipo)
            
            response = query.execute()
            
            # Processar dados para incluir métricas
            canais = []
            for item in response.data:
                canal = {
                    "id": item["id"],
                    "nome_canal": item["nome_canal"],
                    "url_canal": item["url_canal"],
                    "nicho": item["nicho"],
                    "subnicho": item["subnicho"],
                    "lingua": item.get("lingua", "N/A"),
                    "tipo": item.get("tipo", "minerado"),
                    "status": item["status"],
                    "ultima_coleta": item.get("ultima_coleta"),
                    # Valores padrão caso não tenha dados
                    "views_60d": 0,
                    "views_30d": 0,
                    "views_15d": 0,
                    "views_7d": 0,
                    "inscritos": 0,
                    "engagement_rate": 0.0,
                    "videos_publicados_7d": 0,
                    "score_calculado": 0,
                    "growth_30d": 0,
                    "growth_7d": 0
                }
                
                # Se tiver dados históricos, sobrescrever os valores
                if item.get("dados_canais_historico") and len(item["dados_canais_historico"]) > 0:
                    # Pegar o registro mais recente
                    historico = item["dados_canais_historico"][-1] if isinstance(item["dados_canais_historico"], list) else item["dados_canais_historico"]
                    
                    canal["views_60d"] = historico.get("views_60d", 0) or 0
                    canal["views_30d"] = historico.get("views_30d", 0) or 0
                    canal["views_15d"] = historico.get("views_15d", 0) or 0
                    canal["views_7d"] = historico.get("views_7d", 0) or 0
                    canal["inscritos"] = historico.get("inscritos", 0) or 0
                    canal["engagement_rate"] = historico.get("engagement_rate", 0.0) or 0.0
                    canal["videos_publicados_7d"] = historico.get("videos_publicados_7d", 0) or 0
                    
                    # Calcular score apenas se tiver inscritos
                    if canal["inscritos"] > 0:
                        score = ((canal["views_30d"] / canal["inscritos"]) * 0.7) + \
                               ((canal["views_7d"] / canal["inscritos"]) * 0.3)
                        canal["score_calculado"] = round(score, 2)
                    
                    # Calcular growth
                    if canal["views_30d"] > 0 and canal["views_60d"] > 0:
                        growth = (((canal["views_30d"] - (canal["views_60d"] - canal["views_30d"])) / 
                                  (canal["views_60d"] - canal["views_30d"])) * 100)
                        canal["growth_30d"] = round(growth, 2)
                    
                    if canal["views_7d"] > 0 and canal["views_15d"] > 0:
                        growth = (((canal["views_7d"] - (canal["views_15d"] - canal["views_7d"])) / 
                                  (canal["views_15d"] - canal["views_7d"])) * 100)
                        canal["growth_7d"] = round(growth, 2)
                    
                canais.append(canal)
            
            # Aplicar filtros de valores mínimos
            if views_60d_min:
                canais = [c for c in canais if c.get("views_60d", 0) >= views_60d_min]
            if views_30d_min:
                canais = [c for c in canais if c.get("views_30d", 0) >= views_30d_min]
            if views_15d_min:
                canais = [c for c in canais if c.get("views_15d", 0) >= views_15d_min]
            if views_7d_min:
                canais = [c for c in canais if c.get("views_7d", 0) >= views_7d_min]
            if score_min:
                canais = [c for c in canais if c.get("score_calculado", 0) >= score_min]
            if growth_min:
                canais = [c for c in canais if c.get("growth_7d", 0) >= growth_min]
            
            # Ordenar por score (maiores primeiro)
            canais.sort(key=lambda x: x.get("score_calculado", 0), reverse=True)
            
            # Aplicar paginação
            return canais[offset:offset + limit]
            
        except Exception as e:
            logger.error(f"Error fetching canais with filters: {e}")
            raise

    async def get_videos_with_filters(
        self,
        nicho: Optional[str] = None,
        subnicho: Optional[str] = None,
        lingua: Optional[str] = None,
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
            days_map = {"60d": 60, "30d": 30, "15d": 15, "7d": 7}
            days = days_map.get(periodo_publicacao, 60)
            cutoff_date = (datetime.now() - timedelta(days=days)).isoformat()
            
            query = self.supabase.table("videos_historico").select("*").gte("data_publicacao", cutoff_date)
            
            if views_min:
                query = query.gte("views_atuais", views_min)
            
            desc = order_by in ["views_atuais", "growth_video"]
            query = query.order(order_by, desc=desc)
            query = query.range(offset, offset + limit - 1)
            
            response = query.execute()
            videos = response.data
            
            if videos:
                canal_ids = list(set(v["canal_id"] for v in videos))
                canais_response = self.supabase.table("canais_monitorados").select("*").in_("id", canal_ids).execute()
                canais_dict = {c["id"]: c for c in canais_response.data}
                
                for video in videos:
                    canal_info = canais_dict.get(video["canal_id"], {})
                    video["nome_canal"] = canal_info.get("nome_canal", "Unknown")
                    video["nicho"] = canal_info.get("nicho", "Unknown")
                    video["subnicho"] = canal_info.get("subnicho", "Unknown")
                    video["lingua"] = canal_info.get("lingua", "N/A")
                
                if nicho:
                    videos = [v for v in videos if v.get("nicho") == nicho]
                if subnicho:
                    videos = [v for v in videos if v.get("subnicho") == subnicho]
                if lingua:
                    videos = [v for v in videos if v.get("lingua") == lingua]
                if canal:
                    videos = [v for v in videos if v.get("nome_canal") == canal]
            
            return videos
        except Exception as e:
            logger.error(f"Error fetching videos with filters: {e}")
            raise

    async def get_filter_options(self) -> Dict[str, List]:
        """Get available filter options"""
        try:
            nichos_response = self.supabase.table("canais_monitorados").select("nicho").execute()
            nichos = list(set(item["nicho"] for item in nichos_response.data if item["nicho"]))
            
            subnichos_response = self.supabase.table("canais_monitorados").select("subnicho").execute()
            subnichos = list(set(item["subnicho"] for item in subnichos_response.data if item["subnicho"]))
            
            linguas_response = self.supabase.table("canais_monitorados").select("lingua").execute()
            linguas = list(set(item["lingua"] for item in linguas_response.data if item.get("lingua")))
            
            canais_response = self.supabase.table("canais_monitorados").select("nome_canal").eq("status", "ativo").execute()
            canais = [item["nome_canal"] for item in canais_response.data]
            
            return {
                "nichos": sorted(nichos),
                "subnichos": sorted(subnichos),
                "linguas": sorted(linguas),
                "canais": sorted(canais)
            }
        except Exception as e:
            logger.error(f"Error fetching filter options: {e}")
            raise

    async def get_system_stats(self) -> Dict[str, Any]:
        """Get system statistics"""
        try:
            canais_response = self.supabase.table("canais_monitorados").select("id", count="exact").execute()
            total_canais = canais_response.count
            
            videos_response = self.supabase.table("videos_historico").select("id", count="exact").execute()
            total_videos = videos_response.count
            
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
            
            canal_response = self.supabase.table("dados_canais_historico").delete().lt("data_coleta", cutoff_date).execute()
            video_response = self.supabase.table("videos_historico").delete().lt("data_coleta", cutoff_date).execute()
            
            logger.info(f"Cleaned up old data before {cutoff_date}")
        except Exception as e:
            logger.error(f"Error cleaning up old data: {e}")
            raise

    async def add_favorito(self, tipo: str, item_id: int) -> Dict:
        """Add item to favorites"""
        try:
            existing = self.supabase.table("favoritos").select("*").eq("tipo", tipo).eq("item_id", item_id).execute()
            
            if existing.data:
                logger.info(f"Favorito já existe: tipo={tipo}, item_id={item_id}")
                return existing.data[0]
            
            response = self.supabase.table("favoritos").insert({
                "tipo": tipo,
                "item_id": item_id
            }).execute()
            
            logger.info(f"Added favorito: tipo={tipo}, item_id={item_id}")
            return response.data[0] if response.data else None
        except Exception as e:
            logger.error(f"Error adding favorito: {e}")
            raise

    async def remove_favorito(self, tipo: str, item_id: int):
        """Remove item from favorites"""
        try:
            response = self.supabase.table("favoritos").delete().eq("tipo", tipo).eq("item_id", item_id).execute()
            logger.info(f"Removed favorito: tipo={tipo}, item_id={item_id}")
            return response.data
        except Exception as e:
            logger.error(f"Error removing favorito: {e}")
            raise

    async def get_favoritos_canais(self) -> List[Dict]:
        """Get favorited channels with full data"""
        try:
            favoritos_response = self.supabase.table("favoritos").select("item_id").eq("tipo", "canal").execute()
            
            if not favoritos_response.data:
                return []
            
            canal_ids = [fav["item_id"] for fav in favoritos_response.data]
            canais = await self.get_canais_with_filters(limit=1000)
            canais_favoritos = [c for c in canais if c["id"] in canal_ids]
            
            logger.info(f"Retrieved {len(canais_favoritos)} favorited channels")
            return canais_favoritos
        except Exception as e:
            logger.error(f"Error fetching favoritos canais: {e}")
            raise

    async def get_favoritos_videos(self) -> List[Dict]:
        """Get favorited videos with full data"""
        try:
            favoritos_response = self.supabase.table("favoritos").select("item_id").eq("tipo", "video").execute()
            
            if not favoritos_response.data:
                return []
            
            video_ids = [fav["item_id"] for fav in favoritos_response.data]
            videos_response = self.supabase.table("videos_historico").select("*").in_("id", video_ids).execute()
            videos = videos_response.data
            
            if videos:
                canal_ids = list(set(v["canal_id"] for v in videos))
                canais_response = self.supabase.table("canais_monitorados").select("*").in_("id", canal_ids).execute()
                canais_dict = {c["id"]: c for c in canais_response.data}
                
                for video in videos:
                    canal_info = canais_dict.get(video["canal_id"], {})
                    video["nome_canal"] = canal_info.get("nome_canal", "Unknown")
                    video["nicho"] = canal_info.get("nicho", "Unknown")
                    video["subnicho"] = canal_info.get("subnicho", "Unknown")
                    video["lingua"] = canal_info.get("lingua", "N/A")
            
            logger.info(f"Retrieved {len(videos)} favorited videos")
            return videos
        except Exception as e:
            logger.error(f"Error fetching favoritos videos: {e}")
            raise

    async def delete_canal_permanently(self, canal_id: int):
        """Delete canal and all related data permanently"""
        try:
            self.supabase.table("videos_historico").delete().eq("canal_id", canal_id).execute()
            self.supabase.table("dados_canais_historico").delete().eq("canal_id", canal_id).execute()
            self.supabase.table("favoritos").delete().eq("tipo", "canal").eq("item_id", canal_id).execute()
            self.supabase.table("canais_monitorados").delete().eq("id", canal_id).execute()
            
            logger.info(f"Permanently deleted canal_id {canal_id} and all related data")
            return True
        except Exception as e:
            logger.error(f"Error deleting canal permanently: {e}")
            raise
