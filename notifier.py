"""
Sistema de Notificacoes - Notifier
Verifica videos que atingiram marcos e cria notificacoes automaticamente.
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
        
        Fluxo:
        1. Busca todas as regras ativas
        2. Para cada regra, busca videos que atingiram o marco
        3. Para cada video, verifica se ja tem notificacao vista
        4. Se nao tem, cria notificacao
        """
        try:
            logger.info("=" * 80)
            logger.info("INICIANDO VERIFICACAO DE NOTIFICACOES")
            logger.info("=" * 80)
            
            # Buscar regras ativas
            regras = await self.get_regras_ativas()
            
            if not regras:
                logger.info("Nenhuma regra ativa encontrada. Pulando verificacao.")
                return
            
            logger.info(f"Encontradas {len(regras)} regras ativas")
            
            total_notificacoes = 0
            
            # Processar cada regra
            for regra in regras:
                logger.info("-" * 80)
                logger.info(f"Processando regra: {regra['nome_regra']}")
                logger.info(f"Marco: {regra['views_minimas']} views em {regra['periodo_dias']} dia(s)")
                logger.info(f"Tipo: {regra['tipo_canal']}")
                
                # Buscar videos que atingiram o marco
                videos = await self.get_videos_that_hit_milestone(regra)
                
                if not videos:
                    logger.info("Nenhum video atingiu este marco")
                    continue
                
                logger.info(f"{len(videos)} video(s) atingiram este marco")
                
                # Criar notificacoes para cada video
                for video in videos:
                    # Verificar se video ja tem notificacao vista
                    ja_notificado = await self.video_already_notified(video['video_id'])
                    
                    if ja_notificado:
                        logger.info(f"Video '{video['titulo'][:50]}...' ja foi visto - PULANDO")
                        continue
                    
                    # Criar notificacao
                    await self.create_notification(video, regra)
                    total_notificacoes += 1
                    logger.info(f"NOTIFICACAO CRIADA: '{video['titulo'][:50]}...'")
            
            logger.info("=" * 80)
            logger.info(f"VERIFICACAO COMPLETA - {total_notificacoes} notificacoes criadas")
            logger.info("=" * 80)
            
        except Exception as e:
            logger.error(f"Erro ao verificar notificacoes: {e}")
            import traceback
            logger.error(traceback.format_exc())
    
    
    async def get_regras_ativas(self) -> List[Dict]:
        """
        Busca todas as regras de notificacao que estao ativas.
        
        Returns:
            Lista de regras ativas
        """
        try:
            response = self.db.table("regras_notificacoes").select("*").eq("ativa", True).execute()
            return response.data if response.data else []
        except Exception as e:
            logger.error(f"Erro ao buscar regras ativas: {e}")
            return []
    
    
    async def get_videos_that_hit_milestone(self, regra: Dict) -> List[Dict]:
        """
        Busca videos que atingiram o marco especificado na regra.
        
        Args:
            regra: Dicionario com dados da regra (views_minimas, periodo_dias, tipo_canal)
        
        Returns:
            Lista de videos que atingiram o marco
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
    
    
    async def video_already_notified(self, video_id: str) -> bool:
        """
        Verifica se video ja tem notificacao VISTA.
        
        IMPORTANTE: Apenas verifica notificacoes com vista=true.
        Se usuario ja viu uma notificacao deste video, nao cria mais.
        
        Args:
            video_id: ID do video no YouTube
        
        Returns:
            True se ja existe notificacao vista, False caso contrario
        """
        try:
            response = self.db.table("notificacoes").select("id").eq(
                "video_id", video_id
            ).eq("vista", True).execute()
            
            return len(response.data) > 0 if response.data else False
            
        except Exception as e:
            logger.error(f"Erro ao verificar se video ja foi notificado: {e}")
            return False
    
    
    async def create_notification(self, video: Dict, regra: Dict):
        """
        Cria uma nova notificacao no banco de dados.
        
        Args:
            video: Dicionario com dados do video
            regra: Dicionario com dados da regra
        """
        try:
            # Formatar periodo
            if regra['periodo_dias'] == 1:
                periodo_texto = "24 horas"
            elif regra['periodo_dias'] == 3:
                periodo_texto = "3 dias"
            elif regra['periodo_dias'] == 7:
                periodo_texto = "7 dias"
            elif regra['periodo_dias'] == 14:
                periodo_texto = "2 semanas"
            else:
                periodo_texto = f"{regra['periodo_dias']} dias"
            
            # Formatar views
            views = video['views_atuais']
            if views >= 1000000:
                views_texto = f"{views/1000000:.1f}M"
            elif views >= 1000:
                views_texto = f"{views/1000:.0f}k"
            else:
                views_texto = str(views)
            
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
                'vista': False
            }
            
            response = self.db.table("notificacoes").insert(notification_data).execute()
            
            logger.info(f"Notificacao criada: {mensagem}")
            
        except Exception as e:
            logger.error(f"Erro ao criar notificacao: {e}")
            import traceback
            logger.error(traceback.format_exc())
