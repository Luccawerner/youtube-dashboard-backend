"""
Sistema de Notificacoes - Notifier
Verifica videos que atingiram marcos e cria notificacoes automaticamente.
Com sistema anti-duplicacao e elevacao de notificacoes.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Optional, Any
from supabase import Client

logger = logging.getLogger(__name__)


class NotificationChecker:
    """
    Classe responsavel por verificar videos que atingiram marcos
    e criar notificacoes quando necessario.
    """
    
    def __init__(self, db: Client):
        """
        Inicializa o NotificationChecker.
        
        Args:
            db: Cliente do Supabase para acesso ao banco de dados
        """
        self.db = db
        logger.info("NotificationChecker inicializado")
    
    
    async def check_and_create_notifications(self):
        """
        Funcao principal que verifica e cria notificacoes.
        
        Fluxo com anti-duplicacao:
        1. Busca regras ativas ordenadas por hierarquia
        2. Para cada video que atinge marco:
           - Se ja tem notificacao NAO VISTA e nova regra é maior: ATUALIZA
           - Se ja foi visto alguma vez: PULA
           - Se nao tem notificacao: CRIA
        """
        try:
            logger.info("=" * 80)
            logger.info("INICIANDO VERIFICACAO DE NOTIFICACOES")
            logger.info("=" * 80)
            
            # Buscar regras ativas ORDENADAS por views_minimas (hierarquia)
            regras = await self.get_regras_ativas_ordenadas()
            
            if not regras:
                logger.info("Nenhuma regra ativa encontrada. Pulando verificacao.")
                return
            
            logger.info(f"Encontradas {len(regras)} regras ativas")
            
            total_criadas = 0
            total_atualizadas = 0
            total_puladas = 0
            
            # Processar cada regra (da menor para maior)
            for regra in regras:
                logger.info("-" * 80)
                logger.info(f"Processando regra: {regra['nome_regra']}")
                logger.info(f"Marco: {regra['views_minimas']} views em {regra['periodo_dias']} dia(s)")
                
                # Buscar videos que atingiram o marco
                videos = await self.get_videos_that_hit_milestone(regra)
                
                if not videos:
                    logger.info("Nenhum video atingiu este marco")
                    continue
                
                logger.info(f"{len(videos)} video(s) atingiram este marco")
                
                # Processar cada video
                for video in videos:
                    # Limpar duplicatas antigas antes de processar
                    await self.cleanup_duplicate_notifications(video['video_id'])
                    
                    # Verificar se video ja tem notificacao NAO VISTA
                    notificacao_existente = await self.get_unread_notification(video['video_id'])
                    
                    if notificacao_existente:
                        # Comparar hierarquia de regras
                        regra_anterior = await self.get_regra_by_periodo(notificacao_existente['periodo_dias'])
                        
                        if regra_anterior and regra['views_minimas'] > regra_anterior['views_minimas']:
                            # Nova regra é maior - ATUALIZAR notificação
                            await self.update_notification(notificacao_existente['id'], video, regra)
                            total_atualizadas += 1
                            logger.info(f"✅ NOTIFICACAO ATUALIZADA: '{video['titulo'][:50]}...' ({regra_anterior['nome_regra']} → {regra['nome_regra']})")
                        else:
                            total_puladas += 1
                            logger.info(f"⏭️  Video '{video['titulo'][:50]}...' ja tem notificacao igual ou maior - PULANDO")
                    else:
                        # Verificar se já foi visto alguma vez
                        ja_visto = await self.video_already_seen(video['video_id'])
                        
                        if ja_visto:
                            total_puladas += 1
                            logger.info(f"👁️  Video '{video['titulo'][:50]}...' ja foi visto anteriormente - PULANDO")
                            continue
                        
                        # Criar nova notificacao
                        await self.create_notification(video, regra)
                        total_criadas += 1
                        logger.info(f"🆕 NOTIFICACAO CRIADA: '{video['titulo'][:50]}...'")
            
            logger.info("=" * 80)
            logger.info(f"✅ VERIFICACAO COMPLETA")
            logger.info(f"   Criadas: {total_criadas}")
            logger.info(f"   Atualizadas: {total_atualizadas}")
            logger.info(f"   Puladas: {total_puladas}")
            logger.info("=" * 80)
            
        except Exception as e:
            logger.error(f"Erro ao verificar notificacoes: {e}")
            import traceback
            logger.error(traceback.format_exc())
    
    
    async def get_regras_ativas_ordenadas(self) -> List[Dict]:
        """
        Busca regras ativas ORDENADAS por views_minimas (hierarquia).
        Menor para maior: 15k → 50k → 100k → 150k
        """
        try:
            response = self.db.table("regras_notificacoes")\
                .select("*")\
                .eq("ativa", True)\
                .order("views_minimas")\
                .execute()
            return response.data if response.data else []
        except Exception as e:
            logger.error(f"Erro ao buscar regras ativas: {e}")
            return []
    
    
    async def get_unread_notification(self, video_id: str) -> Optional[Dict]:
        """
        Busca notificação NAO VISTA do vídeo.
        Retorna apenas a primeira (mais recente).
        """
        try:
            response = self.db.table("notificacoes")\
                .select("*")\
                .eq("video_id", video_id)\
                .eq("vista", False)\
                .order("created_at.desc")\
                .limit(1)\
                .execute()
            
            if response.data and len(response.data) > 0:
                return response.data[0]
            return None
            
        except Exception as e:
            logger.error(f"Erro ao buscar notificacao nao vista: {e}")
            return None
    
    
    async def get_regra_by_periodo(self, periodo_dias: int) -> Optional[Dict]:
        """Busca regra ativa pelo período de dias"""
        try:
            response = self.db.table("regras_notificacoes")\
                .select("*")\
                .eq("periodo_dias", periodo_dias)\
                .eq("ativa", True)\
                .limit(1)\
                .execute()
            
            if response.data and len(response.data) > 0:
                return response.data[0]
            return None
            
        except Exception as e:
            logger.error(f"Erro ao buscar regra por periodo: {e}")
            return None
    
    
    async def video_already_seen(self, video_id: str) -> bool:
        """
        Verifica se video ja teve notificacao VISTA alguma vez.
        Se sim, nunca mais cria notificação deste vídeo.
        """
        try:
            response = self.db.table("notificacoes")\
                .select("id")\
                .eq("video_id", video_id)\
                .eq("vista", True)\
                .limit(1)\
                .execute()
            
            return len(response.data) > 0 if response.data else False
            
        except Exception as e:
            logger.error(f"Erro ao verificar se video ja foi visto: {e}")
            return False
    
    
    async def cleanup_duplicate_notifications(self, video_id: str):
        """
        Remove notificações duplicadas não vistas do mesmo vídeo.
        Mantém apenas a mais recente.
        """
        try:
            # Buscar todas notificações não vistas do vídeo
            response = self.db.table("notificacoes")\
                .select("id, created_at")\
                .eq("video_id", video_id)\
                .eq("vista", False)\
                .order("created_at.desc")\
                .execute()
            
            if response.data and len(response.data) > 1:
                # Manter apenas a mais recente, deletar as outras
                ids_to_delete = [n['id'] for n in response.data[1:]]
                
                for notif_id in ids_to_delete:
                    self.db.table("notificacoes").delete().eq("id", notif_id).execute()
                
                logger.info(f"🧹 Removidas {len(ids_to_delete)} notificações duplicadas do vídeo")
            
        except Exception as e:
            logger.error(f"Erro ao limpar notificações duplicadas: {e}")
    
    
    async def update_notification(self, notification_id: int, video: Dict, regra: Dict):
        """
        Atualiza notificação existente com nova regra (elevação).
        """
        try:
            # Formatar periodo e views
            periodo_texto = self._formatar_periodo(regra['periodo_dias'])
            views_texto = self._formatar_views(video['views_atuais'])
            
            # Criar mensagem
            mensagem = (
                f"O video '{video['titulo']}' do canal {video['nome_canal']} "
                f"atingiu {views_texto} views nas ultimas {periodo_texto}"
            )
            
            # Tipo de alerta
            tipo_alerta = f"{views_texto}_{regra['periodo_dias']}d"
            
            # Atualizar no banco
            update_data = {
                'views_atingidas': video['views_atuais'],
                'periodo_dias': regra['periodo_dias'],
                'tipo_alerta': tipo_alerta,
                'mensagem': mensagem,
                'data_disparo': datetime.now(timezone.utc).isoformat()
            }
            
            self.db.table("notificacoes")\
                .update(update_data)\
                .eq("id", notification_id)\
                .execute()
            
            logger.info(f"Notificacao atualizada: {mensagem}")
            
        except Exception as e:
            logger.error(f"Erro ao atualizar notificacao: {e}")
            import traceback
            logger.error(traceback.format_exc())
    
    
    async def get_videos_that_hit_milestone(self, regra: Dict) -> List[Dict]:
        """
        Busca videos que atingiram o marco especificado na regra.
        """
        try:
            # Calcular data de corte
            cutoff_date = (datetime.now(timezone.utc) - timedelta(days=regra['periodo_dias'])).isoformat()
            
            # Buscar videos recentes com views suficientes
            query = self.db.table("videos_historico").select(
                "*, canais_monitorados!inner(tipo, nome_canal)"
            ).gte("data_publicacao", cutoff_date).gte("views_atuais", regra['views_minimas'])
            
            # Filtrar por tipo de canal se necessario
            tipo_canal = regra.get('tipo_canal', 'ambos')
            if tipo_canal != 'ambos':
                query = query.eq("canais_monitorados.tipo", tipo_canal)
            
            response = query.execute()
            
            # Processar resultados
            videos = []
            if response.data:
                for item in response.data:
                    videos.append({
                        'video_id': item['video_id'],
                        'titulo': item['titulo'],
                        'canal_id': item['canal_id'],
                        'nome_canal': item.get('canais_monitorados', {}).get('nome_canal', 'Unknown'),
                        'views_atuais': item['views_atuais'],
                        'data_publicacao': item['data_publicacao']
                    })
            
            return videos
            
        except Exception as e:
            logger.error(f"Erro ao buscar videos que atingiram marco: {e}")
            return []
    
    
    async def create_notification(self, video: Dict, regra: Dict):
        """
        Cria uma nova notificacao no banco de dados.
        """
        try:
            # Formatar periodo e views
            periodo_texto = self._formatar_periodo(regra['periodo_dias'])
            views_texto = self._formatar_views(video['views_atuais'])
            
            # Criar mensagem
            mensagem = (
                f"O video '{video['titulo']}' do canal {video['nome_canal']} "
                f"atingiu {views_texto} views nas ultimas {periodo_texto}"
            )
            
            # Tipo de alerta
            tipo_alerta = f"{views_texto}_{regra['periodo_dias']}d"
            
            # Inserir no banco
            notification_data = {
                'video_id': video['video_id'],
                'canal_id': video['canal_id'],
                'nome_video': video['titulo'],
                'nome_canal': video['nome_canal'],
                'views_atingidas': video['views_atuais'],
                'periodo_dias': regra['periodo_dias'],
                'tipo_alerta': tipo_alerta,
                'mensagem': mensagem,
                'vista': False,
                'data_disparo': datetime.now(timezone.utc).isoformat()
            }
            
            self.db.table("notificacoes").insert(notification_data).execute()
            
            logger.info(f"Notificacao criada: {mensagem}")
            
        except Exception as e:
            logger.error(f"Erro ao criar notificacao: {e}")
            import traceback
            logger.error(traceback.format_exc())
    
    
    def _formatar_periodo(self, periodo_dias: int) -> str:
        """Formata período em texto legível"""
        if periodo_dias == 1:
            return "24 horas"
        elif periodo_dias == 3:
            return "3 dias"
        elif periodo_dias == 7:
            return "7 dias"
        elif periodo_dias == 14:
            return "2 semanas"
        else:
            return f"{periodo_dias} dias"
    
    
    def _formatar_views(self, views: int) -> str:
        """Formata views em texto legível"""
        if views >= 1000000:
            return f"{views/1000000:.1f}M"
        elif views >= 1000:
            return f"{views/1000:.0f}k"
        else:
            return str(views)
