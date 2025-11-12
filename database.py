import os
import asyncio
from datetime import datetime, timedelta, timezone
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
        try:
            response = self.supabase.table("canais_monitorados").select("id").limit(1).execute()
            return True
        except Exception as e:
            logger.error(f"Database connection test failed: {e}")
            raise

    async def upsert_canal(self, canal_data: Dict[str, Any]) -> Dict:
        try:
            response = self.supabase.table("canais_monitorados").upsert({
                "nome_canal": canal_data.get("nome_canal"),
                "url_canal": canal_data.get("url_canal"),
                "nicho": canal_data.get("nicho", ""),
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
        try:
            response = self.supabase.table("canais_monitorados").select("*").eq("status", "ativo").execute()
            logger.info(f"Found {len(response.data)} canais needing collection")
            return response.data
        except Exception as e:
            logger.error(f"Error getting canais for collection: {e}")
            raise

    async def save_canal_data(self, canal_id: int, data: Dict[str, Any]):
        try:
            data_coleta = datetime.now(timezone.utc).date().isoformat()
            
            # 🔧 CORREÇÃO: Voltei a checar views_60d (não gasta API, é só validação!)
            views_60d = data.get("views_60d", 0)
            views_30d = data.get("views_30d", 0)
            views_15d = data.get("views_15d", 0)
            views_7d = data.get("views_7d", 0)
            
            # Check if at least one view metric is > 0
            if views_60d == 0 and views_30d == 0 and views_15d == 0 and views_7d == 0:
                logger.warning(f"Skipping save for canal_id {canal_id} - all views zero")
                return None
            
            existing = self.supabase.table("dados_canais_historico").select("*").eq("canal_id", canal_id).eq("data_coleta", data_coleta).execute()
            
            canal_data = {
                "canal_id": canal_id,
                "data_coleta": data_coleta,
                "views_30d": data.get("views_30d"),
                "views_15d": data.get("views_15d"),
                "views_7d": data.get("views_7d"),
                "inscritos": data.get("inscritos"),
                "videos_publicados_7d": data.get("videos_publicados_7d", 0),
                "engagement_rate": data.get("engagement_rate", 0.0)
            }
            
            if existing.data:
                response = self.supabase.table("dados_canais_historico").update(canal_data).eq("canal_id", canal_id).eq("data_coleta", data_coleta).execute()
            else:
                response = self.supabase.table("dados_canais_historico").insert(canal_data).execute()
            
            return response.data
        except Exception as e:
            logger.error(f"Error saving canal data: {e}")
            raise

    async def save_videos_data(self, canal_id: int, videos: List[Dict[str, Any]]):
        try:
            if not videos:
                return []
                
            current_date = datetime.now(timezone.utc).date().isoformat()
            
            saved_videos = []
            for video in videos:
                try:
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
                    
                    existing = self.supabase.table("videos_historico").select("id").eq("video_id", video_data["video_id"]).eq("data_coleta", current_date).execute()
                    
                    if existing.data:
                        response = self.supabase.table("videos_historico").update(video_data).eq("video_id", video_data["video_id"]).eq("data_coleta", current_date).execute()
                    else:
                        response = self.supabase.table("videos_historico").insert(video_data).execute()
                    
                    if response.data:
                        saved_videos.extend(response.data)
                        
                except Exception as video_error:
                    logger.warning(f"Error saving individual video {video.get('video_id')}: {video_error}")
                    continue
            
            logger.info(f"Saved {len(saved_videos)} videos for canal {canal_id}")
            return saved_videos
            
        except Exception as e:
            logger.error(f"Error saving videos data: {e}")
            raise

    async def update_last_collection(self, canal_id: int):
        try:
            response = self.supabase.table("canais_monitorados").update({
                "ultima_coleta": datetime.now(timezone.utc).isoformat()
            }).eq("id", canal_id).execute()
            return response.data
        except Exception as e:
            logger.error(f"Error updating last collection: {e}")
            raise

    async def create_coleta_log(self, canais_total: int) -> int:
        try:
            response = self.supabase.table("coletas_historico").insert({
                "data_inicio": datetime.now(timezone.utc).isoformat(),
                "status": "em_progresso",
                "canais_total": canais_total,
                "canais_sucesso": 0,
                "canais_erro": 0,
                "videos_coletados": 0,
                "requisicoes_usadas": 0
            }).execute()
            
            coleta_id = response.data[0]["id"]
            return coleta_id
        except Exception as e:
            logger.error(f"Error creating coleta log: {e}")
            raise

    async def update_coleta_log(self, coleta_id: int, status: str, canais_sucesso: int, canais_erro: int, videos_coletados: int, requisicoes_usadas: int = 0, mensagem_erro: Optional[str] = None):
        try:
            data_inicio_response = self.supabase.table("coletas_historico").select("data_inicio").eq("id", coleta_id).execute()
            
            if data_inicio_response.data:
                data_inicio = datetime.fromisoformat(data_inicio_response.data[0]["data_inicio"].replace('Z', '+00:00'))
                data_fim = datetime.now(timezone.utc)
                duracao = int((data_fim - data_inicio).total_seconds())
            else:
                duracao = 0
            
            update_data = {
                "data_fim": datetime.now(timezone.utc).isoformat(),
                "status": status,
                "canais_sucesso": canais_sucesso,
                "canais_erro": canais_erro,
                "videos_coletados": videos_coletados,
                "duracao_segundos": duracao,
                "requisicoes_usadas": requisicoes_usadas
            }
            
            if mensagem_erro:
                update_data["mensagem_erro"] = mensagem_erro
            
            response = self.supabase.table("coletas_historico").update(update_data).eq("id", coleta_id).execute()
            
            return response.data
        except Exception as e:
            logger.error(f"Error updating coleta log: {e}")
            raise

    async def get_coletas_historico(self, limit: int = 20) -> List[Dict]:
        try:
            response = self.supabase.table("coletas_historico").select("*").order("data_inicio", desc=True).limit(limit).execute()
            return response.data if response.data else []
        except Exception as e:
            logger.error(f"Error fetching coletas historico: {e}")
            raise

    async def cleanup_stuck_collections(self) -> int:
        try:
            # Aumentado de 1h para 2h - coletas demoram 60-80min para 263 canais
            duas_horas_atras = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()

            response = self.supabase.table("coletas_historico").update({
                "status": "erro",
                "mensagem_erro": "Coleta travada - marcada como erro automaticamente (timeout 2h)"
            }).eq("status", "em_progresso").lt("data_inicio", duas_horas_atras).execute()

            count = len(response.data) if response.data else 0
            if count > 0:
                logger.info(f"Cleaned up {count} stuck collections (timeout: 2 hours)")

            return count
        except Exception as e:
            logger.error(f"Error cleaning up stuck collections: {e}")
            return 0

    async def delete_coleta(self, coleta_id: int):
        try:
            response = self.supabase.table("coletas_historico").delete().eq("id", coleta_id).execute()
            return response.data
        except Exception as e:
            logger.error(f"Error deleting coleta: {e}")
            raise

    async def get_quota_diaria_usada(self) -> int:
        try:
            hoje = datetime.now(timezone.utc).date().isoformat()
            
            response = self.supabase.table("coletas_historico").select("requisicoes_usadas").gte("data_inicio", hoje).execute()
            
            total = sum(coleta.get("requisicoes_usadas", 0) for coleta in response.data)
            
            return total
        except Exception as e:
            logger.error(f"Error getting daily quota: {e}")
            return 0

    async def get_canais_with_filters(self, nicho: Optional[str] = None, subnicho: Optional[str] = None, lingua: Optional[str] = None, tipo: Optional[str] = None, views_30d_min: Optional[int] = None, views_15d_min: Optional[int] = None, views_7d_min: Optional[int] = None, score_min: Optional[float] = None, growth_min: Optional[float] = None, limit: int = 500, offset: int = 0) -> List[Dict]:
        try:
            # 🔧 CORREÇÃO CRÍTICA: Buscar apenas histórico dos últimos 2 dias
            # Isso garante que sempre pega os dados MAIS RECENTES e evita carregar dados antigos
            dois_dias_atras = (datetime.now(timezone.utc) - timedelta(days=2)).date().isoformat()
            
            logger.info(f"📊 Buscando histórico a partir de: {dois_dias_atras}")
            
            query = self.supabase.table("canais_monitorados").select("*").eq("status", "ativo")
            
            if nicho:
                query = query.eq("nicho", nicho)
            if subnicho:
                query = query.eq("subnicho", subnicho)
            if lingua:
                query = query.eq("lingua", lingua)
            if tipo:
                query = query.eq("tipo", tipo)
            
            canais_response = query.execute()
            
            # 🔧 BUSCAR APENAS HISTÓRICO RECENTE (últimos 2 dias)
            historico_response = self.supabase.table("dados_canais_historico")\
                .select("*")\
                .gte("data_coleta", dois_dias_atras)\
                .execute()
            
            logger.info(f"📊 Histórico carregado: {len(historico_response.data)} linhas (otimizado)")
            
            # 🔧 Pegar o MAIS RECENTE de cada canal (ordenando por data DESC)
            historico_dict = {}
            for h in historico_response.data:
                canal_id = h["canal_id"]
                data_coleta = h.get("data_coleta", "")
                
                if canal_id not in historico_dict:
                    historico_dict[canal_id] = h
                elif data_coleta > historico_dict[canal_id].get("data_coleta", ""):
                    # 🔧 SEMPRE pega o mais recente
                    historico_dict[canal_id] = h
            
            logger.info(f"📊 Canais com histórico: {len(historico_dict)}")
            
            canais = []
            for item in canais_response.data:
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
                
                # 🔧 Se tem histórico recente, usa ele
                if item["id"] in historico_dict:
                    h = historico_dict[item["id"]]
                    
                    canal["views_30d"] = h.get("views_30d", 0)
                    canal["views_15d"] = h.get("views_15d", 0)
                    canal["views_7d"] = h.get("views_7d", 0)
                    canal["inscritos"] = h.get("inscritos", 0)
                    canal["engagement_rate"] = h.get("engagement_rate", 0.0)
                    canal["videos_publicados_7d"] = h.get("videos_publicados_7d", 0)
                    
                    # Calcular score
                    if canal["inscritos"] > 0:
                        score = ((canal["views_30d"] / canal["inscritos"]) * 0.7) + ((canal["views_7d"] / canal["inscritos"]) * 0.3)
                        canal["score_calculado"] = round(score, 2)
                    
                    # Calcular growth 7d
                    if canal["views_7d"] > 0 and canal["views_15d"] > 0:
                        views_anterior_7d = canal["views_15d"] - canal["views_7d"]
                        if views_anterior_7d > 0:
                            growth = ((canal["views_7d"] - views_anterior_7d) / views_anterior_7d) * 100
                            canal["growth_7d"] = round(growth, 2)
                
                canais.append(canal)
            
            # Aplicar filtros numéricos
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
            
            # Ordenar por score
            canais.sort(key=lambda x: x.get("score_calculado", 0), reverse=True)
            
            logger.info(f"✅ Retornando {len(canais)} canais filtrados")
            
            return canais[offset:offset + limit]
            
        except Exception as e:
            logger.error(f"Error fetching canais with filters: {e}")
            import traceback
            logger.error(traceback.format_exc())
            raise

    async def get_videos_with_filters(self, nicho: Optional[str] = None, subnicho: Optional[str] = None, lingua: Optional[str] = None, canal: Optional[str] = None, periodo_publicacao: str = "30d", views_min: Optional[int] = None, growth_min: Optional[float] = None, order_by: str = "views_atuais", limit: int = 500, offset: int = 0) -> List[Dict]:
        try:
            days_map = {"30d": 30, "15d": 15, "7d": 7}
            days = days_map.get(periodo_publicacao, 30)
            cutoff_date = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
            
            all_videos_response = self.supabase.table("videos_historico").select("*").gte("data_publicacao", cutoff_date).execute()
            
            videos_dict = {}
            for video in all_videos_response.data:
                video_id = video["video_id"]
                data_coleta = video.get("data_coleta", "")
                
                if video_id not in videos_dict:
                    videos_dict[video_id] = video
                elif data_coleta > videos_dict[video_id].get("data_coleta", ""):
                    videos_dict[video_id] = video
            
            videos = list(videos_dict.values())
            
            if views_min:
                videos = [v for v in videos if v.get("views_atuais", 0) >= views_min]
            
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
            import traceback
            logger.error(traceback.format_exc())
            raise
            
    async def get_filter_options(self) -> Dict[str, List]:
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
        try:
            cutoff_date = (datetime.now(timezone.utc) - timedelta(days=60)).date().isoformat()
            
            canal_response = self.supabase.table("dados_canais_historico").delete().lt("data_coleta", cutoff_date).execute()
            video_response = self.supabase.table("videos_historico").delete().lt("data_coleta", cutoff_date).execute()
            
            logger.info(f"Cleaned up old data before {cutoff_date}")
        except Exception as e:
            logger.error(f"Error cleaning up old data: {e}")
            raise

    async def add_favorito(self, tipo: str, item_id: int) -> Dict:
        try:
            existing = self.supabase.table("favoritos").select("*").eq("tipo", tipo).eq("item_id", item_id).execute()
            
            if existing.data:
                return existing.data[0]
            
            response = self.supabase.table("favoritos").insert({
                "tipo": tipo,
                "item_id": item_id
            }).execute()
            
            return response.data[0] if response.data else None
        except Exception as e:
            logger.error(f"Error adding favorito: {e}")
            raise

    async def remove_favorito(self, tipo: str, item_id: int):
        try:
            response = self.supabase.table("favoritos").delete().eq("tipo", tipo).eq("item_id", item_id).execute()
            return response.data
        except Exception as e:
            logger.error(f"Error removing favorito: {e}")
            raise

    async def get_favoritos_canais(self) -> List[Dict]:
        try:
            favoritos_response = self.supabase.table("favoritos").select("item_id").eq("tipo", "canal").execute()
            
            if not favoritos_response.data:
                return []
            
            canal_ids = [fav["item_id"] for fav in favoritos_response.data]
            canais = await self.get_canais_with_filters(limit=1000)
            canais_favoritos = [c for c in canais if c["id"] in canal_ids]
            
            return canais_favoritos
        except Exception as e:
            logger.error(f"Error fetching favoritos canais: {e}")
            raise

    async def get_favoritos_videos(self) -> List[Dict]:
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
            
            return videos
        except Exception as e:
            logger.error(f"Error fetching favoritos videos: {e}")
            raise

    async def delete_canal_permanently(self, canal_id: int):
        try:
            self.supabase.table("videos_historico").delete().eq("canal_id", canal_id).execute()
            self.supabase.table("dados_canais_historico").delete().eq("canal_id", canal_id).execute()
            self.supabase.table("favoritos").delete().eq("tipo", "canal").eq("item_id", canal_id).execute()
            self.supabase.table("canais_monitorados").delete().eq("id", canal_id).execute()
            
            return True
        except Exception as e:
            logger.error(f"Error deleting canal permanently: {e}")
            raise

    async def get_notificacoes_all(self, limit: int = 500, offset: int = 0, vista_filter: Optional[bool] = None, dias: Optional[int] = 30) -> List[Dict]:
        try:
            query = self.supabase.table("notificacoes").select(
                "*, canais_monitorados(subnicho)"
            )
            
            if dias is not None:
                data_limite = (datetime.now(timezone.utc) - timedelta(days=dias)).isoformat()
                query = query.gte("data_disparo", data_limite)
            
            if vista_filter is not None:
                query = query.eq("vista", vista_filter)
            
            response = query.order("data_disparo", desc=True).range(offset, offset + limit - 1).execute()
            
            if not response.data:
                return []
            
            notificacoes = response.data
            
            video_ids = [n["video_id"] for n in notificacoes if n.get("video_id")]
            
            if video_ids:
                videos_response = self.supabase.table("videos_historico").select(
                    "video_id, data_publicacao"
                ).in_("video_id", video_ids).execute()
                
                videos_dict = {v["video_id"]: v["data_publicacao"] for v in videos_response.data}
                
                for notif in notificacoes:
                    video_id = notif.get("video_id")
                    if video_id and video_id in videos_dict:
                        notif["data_publicacao"] = videos_dict[video_id]
                    else:
                        notif["data_publicacao"] = None
            
            for notif in notificacoes:
                if notif.get("canais_monitorados") and notif["canais_monitorados"].get("subnicho"):
                    notif["subnicho"] = notif["canais_monitorados"]["subnicho"]
                else:
                    notif["subnicho"] = None
                notif.pop("canais_monitorados", None)
            
            return notificacoes
        except Exception as e:
            logger.error(f"Erro ao buscar notificacoes: {e}")
            return []
    
    async def marcar_notificacao_vista(self, notif_id: int) -> bool:
        """
        Marca uma notificação como vista.
        """
        try:
            response = self.supabase.table("notificacoes").update({
                "vista": True,
                "data_vista": datetime.now(timezone.utc).isoformat()
            }).eq("id", notif_id).execute()
            
            return True
        except Exception as e:
            logger.error(f"Erro ao marcar notificacao como vista: {e}")
            return False
    
    async def desmarcar_notificacao_vista(self, notif_id: int) -> bool:
        """
        Desmarca uma notificação como vista (volta para não vista).
        Útil quando usuário marca por engano.
        
        Args:
            notif_id: ID da notificação
            
        Returns:
            bool: True se sucesso, False se notificação não encontrada
        """
        try:
            response = self.supabase.table("notificacoes").update({
                "vista": False,
                "data_vista": None
            }).eq("id", notif_id).execute()
            
            return True
        except Exception as e:
            logger.error(f"Erro ao desmarcar notificacao como vista: {e}")
            return False
    
    async def marcar_todas_notificacoes_vistas(self) -> int:
        """
        Marca todas as notificações não vistas como vistas.
        """
        try:
            response = self.supabase.table("notificacoes").update({
                "vista": True,
                "data_vista": datetime.now(timezone.utc).isoformat()
            }).eq("vista", False).execute()
            
            return len(response.data) if response.data else 0
        except Exception as e:
            logger.error(f"Erro ao marcar todas notificacoes como vistas: {e}")
            return 0
    
    async def get_notificacao_stats(self) -> Dict:
        try:
            total_response = self.supabase.table("notificacoes").select("id", count="exact").execute()
            total = total_response.count if total_response.count else 0
            
            nao_vistas_response = self.supabase.table("notificacoes").select("id", count="exact").eq("vista", False).execute()
            nao_vistas = nao_vistas_response.count if nao_vistas_response.count else 0
            
            vistas = total - nao_vistas
            
            hoje = datetime.now(timezone.utc).date().isoformat()
            hoje_response = self.supabase.table("notificacoes").select("id", count="exact").gte("data_disparo", hoje).execute()
            hoje_count = hoje_response.count if hoje_response.count else 0
            
            semana_atras = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
            semana_response = self.supabase.table("notificacoes").select("id", count="exact").gte("data_disparo", semana_atras).execute()
            semana_count = semana_response.count if semana_response.count else 0
            
            return {
                "total": total,
                "nao_vistas": nao_vistas,
                "vistas": vistas,
                "hoje": hoje_count,
                "esta_semana": semana_count
            }
        except Exception as e:
            logger.error(f"Erro ao buscar estatisticas de notificacoes: {e}")
            return {
                "total": 0,
                "nao_vistas": 0,
                "vistas": 0,
                "hoje": 0,
                "esta_semana": 0
            }
            
    async def get_regras_notificacoes(self) -> List[Dict]:
        try:
            response = self.supabase.table("regras_notificacoes").select("*").order("views_minimas", desc=False).execute()
            return response.data if response.data else []
        except Exception as e:
            logger.error(f"Erro ao buscar regras de notificacoes: {e}")
            return []
    
    async def create_regra_notificacao(self, regra_data: Dict) -> Optional[Dict]:
        try:
            if 'subnichos' in regra_data:
                if regra_data['subnichos'] is None or (isinstance(regra_data['subnichos'], list) and len(regra_data['subnichos']) == 0):
                    regra_data['subnichos'] = None
                elif isinstance(regra_data['subnichos'], str):
                    regra_data['subnichos'] = [regra_data['subnichos']]
            
            response = self.supabase.table("regras_notificacoes").insert(regra_data).execute()
            
            if response.data:
                logger.info(f"✅ Regra criada: {regra_data.get('nome_regra')} com {len(regra_data.get('subnichos', [])) if regra_data.get('subnichos') else 'todos os'} subnicho(s)")
                return response.data[0]
            return None
        except Exception as e:
            logger.error(f"Erro ao criar regra de notificacao: {e}")
            return None
    
    async def update_regra_notificacao(self, regra_id: int, regra_data: Dict) -> Optional[Dict]:
        try:
            if 'subnichos' in regra_data:
                if regra_data['subnichos'] is None or (isinstance(regra_data['subnichos'], list) and len(regra_data['subnichos']) == 0):
                    regra_data['subnichos'] = None
                elif isinstance(regra_data['subnichos'], str):
                    regra_data['subnichos'] = [regra_data['subnichos']]
            
            response = self.supabase.table("regras_notificacoes").update(regra_data).eq("id", regra_id).execute()
            
            if response.data:
                logger.info(f"✅ Regra atualizada: ID {regra_id}")
                return response.data[0]
            return None
        except Exception as e:
            logger.error(f"Erro ao atualizar regra de notificacao: {e}")
            return None
    
    async def delete_regra_notificacao(self, regra_id: int) -> bool:
        try:
            response = self.supabase.table("regras_notificacoes").delete().eq("id", regra_id).execute()
            return True
        except Exception as e:
            logger.error(f"Erro ao deletar regra de notificacao: {e}")
            return False
    
    async def toggle_regra_notificacao(self, regra_id: int) -> Optional[Dict]:
        try:
            current = self.supabase.table("regras_notificacoes").select("ativa").eq("id", regra_id).execute()
            
            if not current.data:
                return None
            
            nova_ativa = not current.data[0]["ativa"]
            
            response = self.supabase.table("regras_notificacoes").update({
                "ativa": nova_ativa
            }).eq("id", regra_id).execute()
            
            return response.data[0] if response.data else None
        except Exception as e:
            logger.error(f"Erro ao toggle regra de notificacao: {e}")
            return None

    async def get_cached_transcription(self, video_id: str):
        try:
            response = self.supabase.table("transcriptions").select("*").eq("video_id", video_id).execute()
            
            if response.data and len(response.data) > 0:
                logger.info(f"✅ Cache hit for video: {video_id}")
                return response.data[0]["transcription"]
            
            logger.info(f"❌ Cache miss for video: {video_id}")
            return None
        except Exception as e:
            logger.error(f"Error fetching cached transcription: {e}")
            return None
    
    async def save_transcription_cache(self, video_id: str, transcription: str):
        try:
            data = {
                "video_id": video_id,
                "transcription": transcription,
                "updated_at": datetime.now(timezone.utc).isoformat()
            }
            
            response = self.supabase.table("transcriptions").upsert(data).execute()
            
            logger.info(f"💾 Transcription cached for video: {video_id}")
            return response.data[0] if response.data else None
        except Exception as e:
            logger.error(f"Error saving transcription cache: {e}")
            return None

    # =========================================================================
    # ANALYSIS TAB - New Functions
    # Added by Claude Code - 2024-11-05
    # =========================================================================

    async def get_keyword_analysis(self, period_days: int = 30) -> List[Dict]:
        """Busca análise de keywords mais recente"""
        try:
            today = datetime.now().strftime("%Y-%m-%d")
            
            response = self.supabase.table("keyword_analysis")\
                .select("*")\
                .eq("period_days", period_days)\
                .eq("analyzed_date", today)\
                .order("frequency", desc=True)\
                .limit(20)\
                .execute()
            
            return response.data if response.data else []
        except Exception as e:
            logger.error(f"Erro ao buscar keyword analysis: {e}")
            return []

    async def get_title_patterns(self, subniche: str, period_days: int = 30) -> List[Dict]:
        """Busca padrões de título por subniche"""
        try:
            today = datetime.now().strftime("%Y-%m-%d")
            
            response = self.supabase.table("title_patterns")\
                .select("*")\
                .eq("subniche", subniche)\
                .eq("period_days", period_days)\
                .eq("analyzed_date", today)\
                .order("avg_views", desc=True)\
                .limit(5)\
                .execute()
            
            return response.data if response.data else []
        except Exception as e:
            logger.error(f"Erro ao buscar title patterns: {e}")
            return []

    async def get_top_channels_snapshot(self, subniche: str) -> List[Dict]:
        """Busca top 5 canais por subniche (snapshot mais recente)"""
        try:
            today = datetime.now().strftime("%Y-%m-%d")
            
            response = self.supabase.table("top_channels_snapshot")\
                .select("*, canais_monitorados!inner(nome_canal, url_canal)")\
                .eq("subniche", subniche)\
                .eq("snapshot_date", today)\
                .order("rank_position", desc=False)\
                .limit(5)\
                .execute()
            
            return response.data if response.data else []
        except Exception as e:
            logger.error(f"Erro ao buscar top channels: {e}")
            return []

    async def get_gap_analysis(self, subniche: str = None) -> List[Dict]:
        """Busca gap analysis mais recente"""
        try:
            week_start = (datetime.now() - timedelta(days=datetime.now().weekday())).strftime("%Y-%m-%d")
            
            query = self.supabase.table("gap_analysis")\
                .select("*")\
                .eq("analyzed_week_start", week_start)
            
            if subniche:
                query = query.eq("subniche", subniche)
            
            response = query.order("avg_views", desc=True).execute()
            
            return response.data if response.data else []
        except Exception as e:
            logger.error(f"Erro ao buscar gap analysis: {e}")
            return []

    async def get_weekly_report_latest(self) -> Optional[Dict]:
        """Busca o relatório semanal mais recente"""
        try:
            response = self.supabase.table("weekly_reports")\
                .select("*")\
                .order("week_start", desc=True)\
                .limit(1)\
                .execute()
            
            if response.data:
                import json
                report = response.data[0]
                report['report_data'] = json.loads(report['report_data'])
                return report
            
            return None
        except Exception as e:
            logger.error(f"Erro ao buscar weekly report: {e}")
            return None

    async def get_all_subniches(self) -> List[str]:
        """Busca lista de todos os subniches ativos"""
        try:
            response = self.supabase.table("canais_monitorados")\
                .select("subnicho")\
                .eq("status", "ativo")\
                .execute()

            if response.data:
                subniches = list(set([c['subnicho'] for c in response.data]))
                return sorted(subniches)

            return []
        except Exception as e:
            logger.error(f"Erro ao buscar subniches: {e}")
            return []

    # =========================================================================
    # SUBNICHE TRENDS SNAPSHOT - New Functions
    # Added by Claude Code - 2025-01-07
    # =========================================================================

    async def save_subniche_trends_snapshot(self, trends_data: List[Dict]) -> bool:
        """
        Salva snapshot de tendências por subniche.

        Args:
            trends_data: Lista de dicts com dados de tendências
                Formato: {
                    'subnicho': str,
                    'period_days': int,
                    'total_videos': int,
                    'avg_views': int,
                    'engagement_rate': float,
                    'trend_percent': float,
                    'analyzed_date': str (YYYY-MM-DD)
                }

        Returns:
            bool: True se sucesso, False se erro
        """
        try:
            if not trends_data:
                logger.warning("Nenhum dado de trends para salvar")
                return False

            today = datetime.now().strftime("%Y-%m-%d")

            # Preparar dados para insert/upsert
            records = []
            for trend in trends_data:
                records.append({
                    "subnicho": trend['subnicho'],
                    "period_days": trend['period_days'],
                    "total_videos": trend.get('total_videos', 0),
                    "avg_views": trend.get('avg_views', 0),
                    "engagement_rate": trend.get('engagement_rate', 0.0),
                    "trend_percent": trend.get('trend_percent', 0.0),
                    "snapshot_date": today,
                    "analyzed_date": trend.get('analyzed_date', today)
                })

            # Upsert: cria novo ou atualiza se já existe (baseado em UNIQUE constraint)
            response = self.supabase.table("subniche_trends_snapshot").upsert(records).execute()

            logger.info(f"✅ Salvos {len(records)} registros de subniche trends")
            return True

        except Exception as e:
            logger.error(f"Erro ao salvar subniche trends snapshot: {e}")
            return False

    async def get_subniche_trends_snapshot(self, period_days: int) -> List[Dict]:
        """
        Busca snapshot mais recente de tendências por subniche.

        Args:
            period_days: Período (7, 15 ou 30 dias)

        Returns:
            Lista de dicts com dados das tendências
        """
        try:
            # Buscar a data mais recente disponível para este período
            latest_date_response = self.supabase.table("subniche_trends_snapshot")\
                .select("analyzed_date")\
                .eq("period_days", period_days)\
                .order("analyzed_date", desc=True)\
                .limit(1)\
                .execute()

            if not latest_date_response.data:
                logger.warning(f"Nenhum snapshot encontrado para {period_days}d")
                return []

            latest_date = latest_date_response.data[0]["analyzed_date"]

            # Buscar todos os dados dessa data mais recente
            response = self.supabase.table("subniche_trends_snapshot")\
                .select("*")\
                .eq("period_days", period_days)\
                .eq("analyzed_date", latest_date)\
                .order("subnicho", desc=False)\
                .execute()

            if response.data:
                logger.info(f"📊 Subniche trends ({period_days}d): {len(response.data)} registros (data: {latest_date})")
                return response.data

            return []

        except Exception as e:
            logger.error(f"Erro ao buscar subniche trends snapshot: {e}")
            return []

    async def get_all_subniche_trends(self) -> Dict[str, List[Dict]]:
        """
        Busca todos os snapshots (7d, 15d, 30d) de uma vez.
        Útil para frontend carregar tudo em uma request.

        Returns:
            Dict com chaves '7d', '15d', '30d' contendo listas de trends
        """
        try:
            trends_7d = await self.get_subniche_trends_snapshot(7)
            trends_15d = await self.get_subniche_trends_snapshot(15)
            trends_30d = await self.get_subniche_trends_snapshot(30)

            return {
                "7d": trends_7d,
                "15d": trends_15d,
                "30d": trends_30d
            }
        except Exception as e:
            logger.error(f"Erro ao buscar all subniche trends: {e}")
            return {"7d": [], "15d": [], "30d": []}
