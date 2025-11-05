from dotenv import load_dotenv
import os

# Carrega variáveis do .env
load_dotenv()

# Debug: verifica se carregou
print(f"SUPABASE_URL carregada: {os.getenv('SUPABASE_URL')[:30] if os.getenv('SUPABASE_URL') else 'NÃO ENCONTRADA'}")
print(f"SUPABASE_KEY carregada: {'SIM' if os.getenv('SUPABASE_KEY') else 'NÃO'}")

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import uvicorn
import os
from datetime import datetime, timedelta, timezone
from typing import Optional, List, Dict, Any
import asyncio
import logging
import uuid
import threading
import time

from database import SupabaseClient
from collector import YouTubeCollector
from notifier import NotificationChecker

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="YouTube Dashboard API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ========================================
# 🆕 MODELOS PYDANTIC
# ========================================

class RegraNotificacaoCreate(BaseModel):
    nome_regra: str
    views_minimas: int
    periodo_dias: int
    tipo_canal: str = "ambos"
    subnichos: Optional[List[str]] = None
    ativa: bool = True

# ========================================
# INICIALIZAÇÃO
# ========================================

db = SupabaseClient()
collector = YouTubeCollector()
notifier = NotificationChecker(db.supabase)

collection_in_progress = False
last_collection_time = None

# ========================================
# SISTEMA DE JOBS ASSÍNCRONOS
# ========================================

transcription_jobs: Dict[str, Dict[str, Any]] = {}
jobs_lock = threading.Lock()

def cleanup_old_jobs():
    """Remove jobs com mais de 1 hora"""
    with jobs_lock:
        now = datetime.now(timezone.utc)
        old_jobs = [
            job_id for job_id, job in transcription_jobs.items()
            if (now - job['created_at']).total_seconds() > 3600
        ]
        for job_id in old_jobs:
            logger.info(f"🧹 Removendo job antigo: {job_id}")
            del transcription_jobs[job_id]

def process_transcription_job(job_id: str, video_id: str):
    """Processa transcrição usando servidor M5 local com polling"""
    try:
        logger.info(f"🎬 [JOB {job_id}] Iniciando transcrição: {video_id}")
        
        with jobs_lock:
            transcription_jobs[job_id]['status'] = 'processing'
            transcription_jobs[job_id]['message'] = 'Iniciando job no servidor M5...'
        
        import requests
        import time
        
        # PASSO 1: Criar job no M5
        logger.info(f"📡 [JOB {job_id}] Criando job no servidor M5...")
        
        response = requests.post(
            "https://transcription.2growai.com.br/transcribe",
            json={
                "video_id": video_id,
                "language": "en"
            },
            timeout=30  # Só para criar o job
        )
        
        if response.status_code != 200:
            raise Exception(f"Servidor M5 retornou erro: {response.status_code}")
        
        data = response.json()
        m5_job_id = data.get('job_id')
        
        if not m5_job_id:
            raise Exception("Servidor M5 não retornou job_id")
        
        logger.info(f"✅ [JOB {job_id}] Job criado no M5: {m5_job_id}")
        
        # PASSO 2: Fazer polling até completar
        max_attempts = 360  # 30 minutos (360 * 5s)
        attempt = 0
        
        while attempt < max_attempts:
            time.sleep(5)  # Aguardar 5 segundos entre checks
            attempt += 1
            
            try:
                status_response = requests.get(
                    f"https://transcription.2growai.com.br/status/{m5_job_id}",
                    timeout=10
                )
                
                if status_response.status_code != 200:
                    continue
                
                status_data = status_response.json()
                m5_status = status_data.get('status')
                
                # Atualizar mensagem
                with jobs_lock:
                    transcription_jobs[job_id]['message'] = status_data.get('message', 'Processando...')
                
                logger.info(f"📊 [JOB {job_id}] Status M5: {m5_status} ({status_data.get('elapsed_seconds')}s)")
                
                # Verificar se completou
                if m5_status == 'completed':
                    result = status_data.get('result', {})
                    transcription = result.get('transcription', '')
                    
                    logger.info(f"✅ [JOB {job_id}] Transcrição completa: {len(transcription)} caracteres")
                    
                    # Salvar no cache
                    asyncio.run(db.save_transcription_cache(video_id, transcription))
                    
                    with jobs_lock:
                        transcription_jobs[job_id]['status'] = 'completed'
                        transcription_jobs[job_id]['message'] = 'Transcrição concluída'
                        transcription_jobs[job_id]['result'] = {
                            'transcription': transcription,
                            'video_id': video_id
                        }
                        transcription_jobs[job_id]['completed_at'] = datetime.now(timezone.utc)
                    
                    logger.info(f"✅ [JOB {job_id}] SUCESSO")
                    return
                
                # Verificar se falhou
                if m5_status == 'failed':
                    error_msg = status_data.get('error', 'Erro desconhecido no servidor M5')
                    raise Exception(error_msg)
                
            except requests.exceptions.RequestException as e:
                logger.warning(f"⚠️ [JOB {job_id}] Erro no polling (tentativa {attempt}): {e}")
                continue
        
        # Timeout
        raise Exception(f"Timeout após {max_attempts * 5} segundos aguardando servidor M5")
        
    except Exception as e:
        logger.error(f"❌ [JOB {job_id}] ERRO: {e}")
        
        with jobs_lock:
            transcription_jobs[job_id]['status'] = 'failed'
            transcription_jobs[job_id]['message'] = str(e)
            transcription_jobs[job_id]['error'] = str(e)
            transcription_jobs[job_id]['failed_at'] = datetime.now(timezone.utc)

# ========================================
# ENDPOINTS DE TRANSCRIÇÃO ASSÍNCRONA
# ========================================

@app.post("/api/transcribe")
async def transcribe_video_async(video_id: str):
    """Inicia transcrição assíncrona - aceita query param"""
    try:
        logger.info(f"🎬 Nova requisição de transcrição: {video_id}")
        
        cleanup_old_jobs()
        
        # Verificar cache primeiro
        cached = await db.get_cached_transcription(video_id)
        if cached:
            logger.info(f"✅ Cache hit para: {video_id}")
            return {
                "status": "completed",
                "from_cache": True,
                "result": {
                    "transcription": cached,
                    "video_id": video_id
                }
            }
        
        job_id = str(uuid.uuid4())
        
        with jobs_lock:
            transcription_jobs[job_id] = {
                'job_id': job_id,
                'video_id': video_id,
                'status': 'queued',
                'message': 'Iniciando processamento...',
                'created_at': datetime.now(timezone.utc),
                'result': None,
                'error': None
            }
        
        thread = threading.Thread(
            target=process_transcription_job,
            args=(job_id, video_id),
            daemon=True
        )
        thread.start()
        
        logger.info(f"🚀 Job criado: {job_id} para vídeo {video_id}")
        
        return {
            "status": "processing",
            "job_id": job_id,
            "video_id": video_id,
            "message": "Transcrição iniciada. Use /api/transcribe/status/{job_id} para verificar progresso."
        }
        
    except Exception as e:
        logger.error(f"❌ Erro ao criar job de transcrição: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/transcribe/status/{job_id}")
async def get_transcription_status(job_id: str):
    """Verifica status do job de transcrição"""
    try:
        with jobs_lock:
            if job_id not in transcription_jobs:
                raise HTTPException(
                    status_code=404, 
                    detail="Job não encontrado. Pode ter expirado (>1h) ou não existir."
                )
            
            job = transcription_jobs[job_id]
        
        elapsed = (datetime.now(timezone.utc) - job['created_at']).total_seconds()
        
        response = {
            "job_id": job['job_id'],
            "video_id": job['video_id'],
            "status": job['status'],
            "message": job['message'],
            "elapsed_seconds": int(elapsed)
        }
        
        if job['status'] == 'completed':
            response['result'] = job['result']
            response['completed_at'] = job['completed_at'].isoformat()
        
        if job['status'] == 'failed':
            response['error'] = job['error']
            response['failed_at'] = job['failed_at'].isoformat()
        
        return response
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Erro ao buscar status do job: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/transcribe/jobs")
async def list_active_jobs():
    """Lista todos os jobs ativos"""
    try:
        with jobs_lock:
            jobs_list = []
            for job_id, job in transcription_jobs.items():
                jobs_list.append({
                    'job_id': job['job_id'],
                    'video_id': job['video_id'],
                    'status': job['status'],
                    'created_at': job['created_at'].isoformat(),
                    'elapsed_seconds': int((datetime.now(timezone.utc) - job['created_at']).total_seconds())
                })
        
        return {
            "total_jobs": len(jobs_list),
            "jobs": jobs_list
        }
        
    except Exception as e:
        logger.error(f"❌ Erro ao listar jobs: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ========================================
# ENDPOINTS ORIGINAIS
# ========================================

@app.get("/")
async def root():
    return {"message": "YouTube Dashboard API is running", "status": "healthy", "version": "1.0"}

@app.get("/health")
async def health_check():
    try:
        await db.test_connection()
        
        quota_usada = await db.get_quota_diaria_usada()
        
        return {
            "status": "healthy", 
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "supabase": "connected",
            "youtube_api": "configured",
            "collection_in_progress": collection_in_progress,
            "last_collection": last_collection_time.isoformat() if last_collection_time else None,
            "quota_usada_hoje": quota_usada,
            "active_transcription_jobs": len(transcription_jobs)
        }
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        raise HTTPException(status_code=503, detail="Service unhealthy")

@app.get("/api/canais")
async def get_canais(
    nicho: Optional[str] = None,
    subnicho: Optional[str] = None,
    lingua: Optional[str] = None,
    tipo: Optional[str] = None,
    views_30d_min: Optional[int] = None,
    views_15d_min: Optional[int] = None,
    views_7d_min: Optional[int] = None,
    score_min: Optional[float] = None,
    growth_min: Optional[float] = None,
    limit: Optional[int] = 500,
    offset: Optional[int] = 0
):
    try:
        canais = await db.get_canais_with_filters(
            nicho=nicho,
            subnicho=subnicho,
            lingua=lingua,
            tipo=tipo,
            views_30d_min=views_30d_min,
            views_15d_min=views_15d_min,
            views_7d_min=views_7d_min,
            score_min=score_min,
            growth_min=growth_min,
            limit=limit,
            offset=offset
        )
        return {"canais": canais, "total": len(canais)}
    except Exception as e:
        logger.error(f"Error fetching canais: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/nossos-canais")
async def get_nossos_canais(
    nicho: Optional[str] = None,
    subnicho: Optional[str] = None,
    lingua: Optional[str] = None,
    views_30d_min: Optional[int] = None,
    views_15d_min: Optional[int] = None,
    views_7d_min: Optional[int] = None,
    score_min: Optional[float] = None,
    growth_min: Optional[float] = None,
    limit: Optional[int] = 100,
    offset: Optional[int] = 0
):
    try:
        canais = await db.get_canais_with_filters(
            nicho=nicho,
            subnicho=subnicho,
            lingua=lingua,
            tipo="nosso",
            views_30d_min=views_30d_min,
            views_15d_min=views_15d_min,
            views_7d_min=views_7d_min,
            score_min=score_min,
            growth_min=growth_min,
            limit=limit,
            offset=offset
        )
        return {"canais": canais, "total": len(canais)}
    except Exception as e:
        logger.error(f"Error fetching nossos canais: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/videos")
async def get_videos(
    nicho: Optional[str] = None,
    subnicho: Optional[str] = None,
    lingua: Optional[str] = None,
    canal: Optional[str] = None,
    periodo_publicacao: Optional[str] = "60d",
    views_min: Optional[int] = None,
    growth_min: Optional[float] = None,
    order_by: Optional[str] = "views_atuais",
    limit: Optional[int] = 100,
    offset: Optional[int] = None
):
    try:
        videos = await db.get_videos_with_filters(
            nicho=nicho,
            subnicho=subnicho,
            lingua=lingua,
            canal=canal,
            periodo_publicacao=periodo_publicacao,
            views_min=views_min,
            growth_min=growth_min,
            order_by=order_by,
            limit=limit,
            offset=offset
        )
        return {"videos": videos, "total": len(videos)}
    except Exception as e:
        logger.error(f"Error fetching videos: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/filtros")
async def get_filtros():
    try:
        filtros = await db.get_filter_options()
        return filtros
    except Exception as e:
        logger.error(f"Error fetching filtros: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/add-canal")
async def add_canal_manual(
    nome_canal: str,
    url_canal: str,
    nicho: str = "",
    subnicho: str = "",
    lingua: str = "English",
    tipo: str = "minerado",
    status: str = "ativo"
):
    try:
        canal_data = {
            'nome_canal': nome_canal,
            'url_canal': url_canal,
            'nicho': nicho,
            'subnicho': subnicho,
            'lingua': lingua,
            'tipo': tipo,
            'status': status
        }
        
        result = await db.upsert_canal(canal_data)
        return {"message": "Canal added successfully", "canal": result}
    except Exception as e:
        logger.error(f"Error adding canal: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.put("/api/canais/{canal_id}")
async def update_canal(
    canal_id: int,
    nome_canal: str,
    url_canal: str,
    nicho: str = "",
    subnicho: str = "",
    lingua: str = "English",
    tipo: str = "minerado",
    status: str = "ativo"
):
    try:
        canal_exists = db.supabase.table("canais_monitorados").select("id").eq("id", canal_id).execute()
        if not canal_exists.data:
            raise HTTPException(status_code=404, detail="Canal não encontrado")
        
        response = db.supabase.table("canais_monitorados").update({
            "nome_canal": nome_canal,
            "url_canal": url_canal,
            "nicho": nicho,
            "subnicho": subnicho,
            "lingua": lingua,
            "tipo": tipo,
            "status": status
        }).eq("id", canal_id).execute()
        
        logger.info(f"Canal updated: {nome_canal} (ID: {canal_id})")
        return {"message": "Canal atualizado com sucesso", "canal": response.data[0] if response.data else None}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating canal: {e}")
        raise HTTPException(status_code=500, detail=str(e))

async def can_start_collection() -> tuple[bool, str]:
    global collection_in_progress, last_collection_time
    
    if collection_in_progress:
        return False, "Collection already in progress"
    
    if last_collection_time:
        time_since_last = datetime.now(timezone.utc) - last_collection_time
        cooldown = timedelta(minutes=1)
        
        if time_since_last < cooldown:
            remaining = cooldown - time_since_last
            seconds = int(remaining.total_seconds())
            return False, f"Cooldown: aguarde {seconds}s"
    
    try:
        await db.cleanup_stuck_collections()
    except Exception as e:
        logger.error(f"Error cleaning stuck collections: {e}")
    
    return True, "OK"

@app.post("/api/collect-data")
async def collect_data(background_tasks: BackgroundTasks):
    try:
        can_collect, message = await can_start_collection()
        
        if not can_collect:
            return {"message": message, "status": "blocked"}
        
        background_tasks.add_task(run_collection_job)
        return {"message": "Collection started", "status": "processing"}
    except Exception as e:
        logger.error(f"Error starting collection: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ⬇️⬇️⬇️ ADICIONE ESTE BLOCO AQUI ⬇️⬇️⬇️
@app.post("/api/force-notifier")
async def force_notifier():
    """
    Força execução do notifier manualmente.
    Útil para: testes, debug, ou recuperar notificações perdidas.
    """
    try:
        logger.info("🔔 FORÇANDO EXECUÇÃO DO NOTIFIER (manual)")
        
        # Importar e executar o notifier
        from notifier import NotificationChecker
        
        checker = NotificationChecker(db.supabase)
        await checker.check_and_create_notifications()
        
        logger.info("✅ Notifier executado com sucesso!")
        
        return {
            "status": "success",
            "message": "Notificador executado com sucesso! Verifique as notificações."
        }
    
    except Exception as e:
        logger.error(f"❌ Erro ao executar notifier: {e}")
        import traceback
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))
# ⬆️⬆️⬆️ ATÉ AQUI ⬆️⬆️⬆️

@app.get("/api/stats")
async def get_stats():
    try:
        stats = await db.get_system_stats()
        return stats
    except Exception as e:
        logger.error(f"Error fetching stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/cleanup")
async def cleanup_data():
    try:
        await db.cleanup_old_data()
        return {"message": "Cleanup concluído com sucesso", "status": "success"}
    except Exception as e:
        logger.error(f"Error in cleanup: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/coletas/historico")
async def get_coletas_historico(limit: Optional[int] = 20):
    try:
        historico = await db.get_coletas_historico(limit=limit)
        
        quota_usada = await db.get_quota_diaria_usada()
        
        quota_total = len(collector.api_keys) * 10000  
        quota_disponivel = quota_total - quota_usada
        porcentagem_usada = (quota_usada / quota_total) * 100 if quota_total > 0 else 0
        
        now_utc = datetime.now(timezone.utc)
        next_reset = now_utc.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
        
        brasilia_offset = timedelta(hours=-3)
        next_reset_brasilia = next_reset + brasilia_offset

        chaves_esgotadas_real = min(int(quota_usada // 10000), len(collector.api_keys))
        chaves_ativas_real = len(collector.api_keys) - chaves_esgotadas_real
        
        return {
            "historico": historico,
            "total": len(historico),
            "quota_info": {
                "total_diario": quota_total,
                "usado_hoje": quota_usada,
                "disponivel": quota_disponivel,
                "porcentagem_usada": round(porcentagem_usada, 1),
                "total_chaves": len(collector.api_keys),
                "chaves_ativas": chaves_ativas_real,
                "chaves_esgotadas": chaves_esgotadas_real,
                "chaves_esgotadas_ids": list(collector.exhausted_keys_date.keys()),
                "proximo_reset_utc": next_reset.isoformat(),
                "proximo_reset_local": next_reset_brasilia.strftime("%d/%m/%Y %H:%M (Horário de Brasília)")
            }
        }
    except Exception as e:
        logger.error(f"Error fetching coletas historico: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/coletas/cleanup")
async def cleanup_stuck_collections():
    try:
        count = await db.cleanup_stuck_collections()
        return {"message": f"{count} coletas travadas marcadas como erro", "count": count}
    except Exception as e:
        logger.error(f"Error in cleanup: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/api/coletas/{coleta_id}")
async def delete_coleta(coleta_id: int):
    try:
        await db.delete_coleta(coleta_id)
        return {"message": "Coleta deletada com sucesso"}
    except Exception as e:
        logger.error(f"Error deleting coleta: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/favoritos/adicionar")
async def add_favorito(tipo: str, item_id: int):
    try:
        if tipo not in ["canal", "video"]:
            raise HTTPException(status_code=400, detail="Tipo deve ser 'canal' ou 'video'")
        
        if tipo == "canal":
            canal_exists = db.supabase.table("canais_monitorados").select("id").eq("id", item_id).execute()
            if not canal_exists.data:
                raise HTTPException(status_code=404, detail="Canal não encontrado")
        elif tipo == "video":
            video_exists = db.supabase.table("videos_historico").select("id").eq("id", item_id).execute()
            if not video_exists.data:
                raise HTTPException(status_code=404, detail="Vídeo não encontrado")
        
        result = await db.add_favorito(tipo, item_id)
        return {"message": "Favorito adicionado com sucesso", "favorito": result}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error adding favorito: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/api/favoritos/remover")
async def remove_favorito(tipo: str, item_id: int):
    try:
        if tipo not in ["canal", "video"]:
            raise HTTPException(status_code=400, detail="Tipo deve ser 'canal' ou 'video'")

        await db.remove_favorito(tipo, item_id)
        return {"message": "Favorito removido com sucesso"}
    except Exception as e:
        logger.error(f"Error removing favorito: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/favoritos/canais")
async def get_favoritos_canais():
    try:
        canais = await db.get_favoritos_canais()
        return {"canais": canais, "total": len(canais)}
    except Exception as e:
        logger.error(f"Error fetching favoritos canais: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/favoritos/videos")
async def get_favoritos_videos():
    try:
        videos = await db.get_favoritos_videos()
        return {"videos": videos, "total": len(videos)}
    except Exception as e:
        logger.error(f"Error fetching favoritos videos: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/api/canais/{canal_id}")
async def delete_canal(canal_id: int, permanent: bool = False):
    try:
        if permanent:
            try:
                notif_response = db.supabase.table("notificacoes").delete().eq("canal_id", canal_id).execute()
                deleted_count = len(notif_response.data) if notif_response.data else 0
                logger.info(f"Deleted {deleted_count} notifications for canal {canal_id}")
            except Exception as e:
                logger.warning(f"Error deleting notifications for canal {canal_id}: {e}")
            
            await db.delete_canal_permanently(canal_id)
            return {"message": "Canal deletado permanentemente"}
        else:
            response = db.supabase.table("canais_monitorados").update({
                "status": "inativo"
            }).eq("id", canal_id).execute()
            return {"message": "Canal desativado", "canal": response.data}
    except Exception as e:
        logger.error(f"Error deleting canal: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/notificacoes")
async def get_notificacoes_nao_vistas():
    try:
        notificacoes = await db.get_notificacoes_nao_vistas()
        return {
            "notificacoes": notificacoes,
            "total": len(notificacoes)
        }
    except Exception as e:
        logger.error(f"Error fetching notificacoes: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/notificacoes/todas")
async def get_notificacoes_todas(
    limit: Optional[int] = 500,
    offset: Optional[int] = 0,
    vista: Optional[bool] = None,
    dias: Optional[int] = 30
):
    try:
        notificacoes = await db.get_notificacoes_all(
            limit=limit,
            offset=offset,
            vista_filter=vista,
            dias=dias
        )
        return {
            "notificacoes": notificacoes,
            "total": len(notificacoes)
        }
    except Exception as e:
        logger.error(f"Error fetching all notificacoes: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/notificacoes/historico")
async def get_notificacoes_historico(limit: Optional[int] = 100):
    try:
        notificacoes = await db.get_notificacoes_all(limit=limit, offset=0)
        return {
            "historico": notificacoes,
            "total": len(notificacoes)
        }
    except Exception as e:
        logger.error(f"Error fetching historico: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.put("/api/notificacoes/{notif_id}/marcar-vista")
async def marcar_notificacao_vista(notif_id: int):
    """
    Marca uma notificação como vista.
    """
    try:
        success = await db.marcar_notificacao_vista(notif_id)
        
        if success:
            return {
                "message": "Notificação marcada como vista",
                "notif_id": notif_id
            }
        else:
            raise HTTPException(status_code=404, detail="Notificação não encontrada")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error marking notificacao as vista: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.put("/api/notificacoes/{notif_id}/desmarcar-vista")
async def desmarcar_notificacao_vista(notif_id: int):
    """
    Desmarca uma notificação como vista (volta para não vista).
    Útil quando usuário marca por engano.
    """
    try:
        logger.info(f"🔄 Desmarcando notificação {notif_id} como não vista")
        
        success = await db.desmarcar_notificacao_vista(notif_id)
        
        if success:
            logger.info(f"✅ Notificação {notif_id} desmarcada com sucesso")
            return {
                "message": "Notificação desmarcada como vista",
                "notif_id": notif_id
            }
        else:
            raise HTTPException(status_code=404, detail="Notificação não encontrada")
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Erro ao desmarcar notificação: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/notificacoes/marcar-todas")
async def marcar_todas_notificacoes_vistas():
    try:
        count = await db.marcar_todas_notificacoes_vistas()
        return {
            "message": f"{count} notificações marcadas como vistas",
            "count": count
        }
    except Exception as e:
        logger.error(f"Error marking all notificacoes as vistas: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/notificacoes/stats")
async def get_notificacoes_stats():
    try:
        stats = await db.get_notificacao_stats()
        return stats
    except Exception as e:
        logger.error(f"Error fetching notificacao stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/regras-notificacoes")
async def get_regras_notificacoes():
    try:
        regras = await db.get_regras_notificacoes()
        return {
            "regras": regras,
            "total": len(regras)
        }
    except Exception as e:
        logger.error(f"Error fetching regras: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/regras-notificacoes")
async def create_regra_notificacao(regra: RegraNotificacaoCreate):
    """🆕 Aceita JSON body via Pydantic model"""
    try:
        regra_data = {
            "nome_regra": regra.nome_regra,
            "views_minimas": regra.views_minimas,
            "periodo_dias": regra.periodo_dias,
            "tipo_canal": regra.tipo_canal,
            "subnichos": regra.subnichos,
            "ativa": regra.ativa
        }
        
        result = await db.create_regra_notificacao(regra_data)
        
        if result:
            return {
                "message": "Regra criada com sucesso",
                "regra": result
            }
        else:
            raise HTTPException(status_code=500, detail="Erro ao criar regra")
    except Exception as e:
        logger.error(f"Error creating regra: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.put("/api/regras-notificacoes/{regra_id}")
async def update_regra_notificacao(regra_id: int, regra: RegraNotificacaoCreate):
    """🆕 Aceita JSON body via Pydantic model"""
    try:
        regra_data = {
            "nome_regra": regra.nome_regra,
            "views_minimas": regra.views_minimas,
            "periodo_dias": regra.periodo_dias,
            "tipo_canal": regra.tipo_canal,
            "subnichos": regra.subnichos,
            "ativa": regra.ativa
        }
        
        result = await db.update_regra_notificacao(regra_id, regra_data)
        
        if result:
            return {
                "message": "Regra atualizada com sucesso",
                "regra": result
            }
        else:
            raise HTTPException(status_code=404, detail="Regra não encontrada")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating regra: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/api/regras-notificacoes/{regra_id}")
async def delete_regra_notificacao(regra_id: int):
    try:
        success = await db.delete_regra_notificacao(regra_id)
        
        if success:
            return {"message": "Regra deletada com sucesso"}
        else:
            raise HTTPException(status_code=404, detail="Regra não encontrada")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting regra: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.put("/api/regras-notificacoes/{regra_id}/toggle")
async def toggle_regra_notificacao(regra_id: int):
    try:
        result = await db.toggle_regra_notificacao(regra_id)
        
        if result:
            status = "ativada" if result["ativa"] else "desativada"
            return {
                "message": f"Regra {status} com sucesso",
                "regra": result
            }
        else:
            raise HTTPException(status_code=404, detail="Regra não encontrada")
    except HTTPException:
        raise
    except Exception as e:
# =========================================================================
# ANALYSIS TAB - New Endpoints
# Added by Claude Code - 2024-11-05
# =========================================================================

@app.get("/api/analysis/keywords")
async def get_keywords_analysis(days: int = 30):
    """
    Retorna top 20 keywords dos últimos X dias

    Query params:
        days: 7, 15 ou 30 (padrão: 30)
    """
    try:
        if days not in [7, 15, 30]:
            raise HTTPException(status_code=400, detail="days deve ser 7, 15 ou 30")

        keywords = await db.get_keyword_analysis(period_days=days)

        return {
            "period_days": days,
            "total": len(keywords),
            "keywords": keywords
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting keywords analysis: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/analysis/title-patterns")
async def get_title_patterns_analysis(subniche: str, days: int = 30):
    """
    Retorna top 5 padrões de título por subniche

    Query params:
        subniche: Nome do subniche (obrigatório)
        days: 7, 15 ou 30 (padrão: 30)
    """
    try:
        if days not in [7, 15, 30]:
            raise HTTPException(status_code=400, detail="days deve ser 7, 15 ou 30")

        patterns = await db.get_title_patterns(subniche=subniche, period_days=days)

        return {
            "subniche": subniche,
            "period_days": days,
            "total": len(patterns),
            "patterns": patterns
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting title patterns: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/analysis/top-channels")
async def get_top_channels_analysis(subniche: str):
    """
    Retorna top 5 canais por subniche (últimos 30 dias)

    Query params:
        subniche: Nome do subniche (obrigatório)
    """
    try:
        channels = await db.get_top_channels_snapshot(subniche=subniche)

        return {
            "subniche": subniche,
            "total": len(channels),
            "channels": channels
        }
    except Exception as e:
        logger.error(f"Error getting top channels: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/analysis/subniches")
async def get_all_subniches():
    """Retorna lista de todos os subniches ativos"""
    try:
        subniches = await db.get_all_subniches()

        return {
            "total": len(subniches),
            "subniches": subniches
        }
    except Exception as e:
        logger.error(f"Error getting subniches: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =========================================================================
# WEEKLY REPORTS - New Endpoints
# =========================================================================

@app.get("/api/reports/weekly/latest")
async def get_latest_weekly_report():
    """Retorna o relatório semanal mais recente"""
    try:
        report = await db.get_weekly_report_latest()

        if report:
            return report
        else:
            raise HTTPException(
                status_code=404,
                detail="Nenhum relatório encontrado. Execute /api/reports/weekly/generate primeiro."
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting weekly report: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/reports/weekly/generate")
async def generate_weekly_report_endpoint():
    """
    Força a geração de um novo relatório semanal

    ATENÇÃO: Processo pode levar alguns minutos
    """
    try:
        from report_generator import ReportGenerator

        logger.info("🔄 Starting weekly report generation...")

        generator = ReportGenerator(db.supabase)
        report = generator.generate_weekly_report()

        logger.info("✅ Weekly report generated successfully")

        return {
            "message": "Relatório gerado com sucesso",
            "report": report
        }
    except Exception as e:
        logger.error(f"Error generating weekly report: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =========================================================================
# ANALYSIS RUNNER - Manual Trigger
# =========================================================================

@app.post("/api/analysis/run-daily")
async def run_daily_analysis():
    """
    Executa análises diárias manualmente

    ATENÇÃO: Processo pode levar alguns minutos
    """
    try:
        from analyzer import Analyzer, save_analysis_to_db

        logger.info("🔄 Starting daily analysis...")

        analyzer = Analyzer(db.supabase)
        subniches = await db.get_all_subniches()

        results = {
            "keywords_analyzed": False,
            "patterns_analyzed": [],
            "channels_analyzed": []
        }

        # Análise de keywords (30, 15, 7 dias)
        for days in [30, 15, 7]:
            logger.info(f"📊 Analyzing keywords ({days} days)...")
            keywords = analyzer.analyze_keywords(period_days=days)
            save_analysis_to_db(db.supabase, 'keywords', keywords, period_days=days)

        results['keywords_analyzed'] = True

        # Análise de padrões e canais por subniche
        for subniche in subniches:
            logger.info(f"📊 Analyzing {subniche}...")

            # Padrões de título
            for days in [30, 15, 7]:
                patterns = analyzer.analyze_title_patterns(subniche, period_days=days)
                save_analysis_to_db(db.supabase, 'patterns', patterns, period_days=days, subniche=subniche)

            results['patterns_analyzed'].append(subniche)

            # Top channels
            channels = analyzer.analyze_top_channels(subniche)
            save_analysis_to_db(db.supabase, 'channels', channels, subniche=subniche)

            results['channels_analyzed'].append(subniche)

        logger.info("✅ Daily analysis completed")

        return {
            "message": "Análise diária executada com sucesso",
            "results": results
        }
    except Exception as e:
        logger.error(f"Error running daily analysis: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/analysis/run-gaps")
async def run_gap_analysis():
    """
    Executa análise de gaps manualmente

    ATENÇÃO: Processo pode levar alguns minutos
    """
    try:
        from analyzer import Analyzer, save_analysis_to_db

        logger.info("🔄 Starting gap analysis...")

        analyzer = Analyzer(db.supabase)
        subniches = await db.get_all_subniches()

        gaps_found = {}

        for subniche in subniches:
            logger.info(f"🔍 Analyzing gaps for {subniche}...")
            gaps = analyzer.analyze_gaps(subniche)
            save_analysis_to_db(db.supabase, 'gaps', gaps, subniche=subniche)
            gaps_found[subniche] = len(gaps)

        logger.info("✅ Gap analysis completed")

        return {
            "message": "Análise de gaps executada com sucesso",
            "gaps_found": gaps_found
        }
    except Exception as e:
        logger.error(f"Error running gap analysis: {e}")
        raise HTTPException(status_code=500, detail=str(e))

        logger.error(f"Error toggling regra: {e}")
        raise HTTPException(status_code=500, detail=str(e))

async def run_collection_job():
    global collection_in_progress, last_collection_time
    
    coleta_id = None
    canais_sucesso = 0
    canais_erro = 0
    videos_total = 0
    
    try:
        collection_in_progress = True
        logger.info("=" * 80)
        logger.info("🚀 STARTING COLLECTION JOB")
        logger.info("=" * 80)
        
        collector.reset_for_new_collection()
        
        canais_to_collect = await db.get_canais_for_collection()
        total_canais = len(canais_to_collect)
        logger.info(f"📊 Found {total_canais} canais to collect")
        
        coleta_id = await db.create_coleta_log(total_canais)
        logger.info(f"📝 Created coleta log ID: {coleta_id}")
        
        for index, canal in enumerate(canais_to_collect, 1):
            if collector.all_keys_exhausted():
# =========================================================================
# CRON JOBS - Daily Analysis + Weekly Report
# Added by Claude Code - 2024-11-05
# =========================================================================

async def run_daily_analysis_job():
    """
    Executa análises diárias após a coleta de dados

    Chamado automaticamente após run_collection_job()
    """
    try:
        from analyzer import Analyzer, save_analysis_to_db

        logger.info("=" * 80)
        logger.info("📊 STARTING DAILY ANALYSIS JOB")
        logger.info("=" * 80)

        analyzer = Analyzer(db.supabase)
        subniches = await db.get_all_subniches()

        # 1. Análise de keywords (30, 15, 7 dias)
        logger.info("🔍 Analyzing keywords...")
        for days in [30, 15, 7]:
            keywords = analyzer.analyze_keywords(period_days=days)
            save_analysis_to_db(db.supabase, 'keywords', keywords, period_days=days)
            logger.info(f"   ✅ Keywords analyzed ({days} days): {len(keywords)} found")

        # 2. Análise de padrões e top channels por subniche
        for subniche in subniches:
            logger.info(f"📝 Analyzing {subniche}...")

            # Padrões de título
            for days in [30, 15, 7]:
                patterns = analyzer.analyze_title_patterns(subniche, period_days=days)
                save_analysis_to_db(db.supabase, 'patterns', patterns, period_days=days, subniche=subniche)

            # Top channels
            channels = analyzer.analyze_top_channels(subniche)
            save_analysis_to_db(db.supabase, 'channels', channels, subniche=subniche)

            logger.info(f"   ✅ {subniche} analysis completed")

        logger.info("=" * 80)
        logger.info("✅ DAILY ANALYSIS COMPLETED")
        logger.info("=" * 80)

    except Exception as e:
        logger.error("=" * 80)
        logger.error(f"❌ DAILY ANALYSIS FAILED: {e}")
        logger.error("=" * 80)


async def run_weekly_report_job():
    """
    Gera relatório semanal completo

    Executado aos domingos às 23h (após daily analysis)
    """
    try:
        from report_generator import ReportGenerator
        from analyzer import Analyzer, save_analysis_to_db

        logger.info("=" * 80)
        logger.info("📊 STARTING WEEKLY REPORT JOB")
        logger.info("=" * 80)

        # 1. Executar gap analysis primeiro
        logger.info("🔍 Running gap analysis...")

        analyzer = Analyzer(db.supabase)
        subniches = await db.get_all_subniches()

        for subniche in subniches:
            gaps = analyzer.analyze_gaps(subniche)
            save_analysis_to_db(db.supabase, 'gaps', gaps, subniche=subniche)
            logger.info(f"   ✅ {subniche}: {len(gaps)} gaps found")

        # 2. Gerar relatório completo
        logger.info("📄 Generating weekly report...")

        generator = ReportGenerator(db.supabase)
        report = generator.generate_weekly_report()

        logger.info("=" * 80)
        logger.info("✅ WEEKLY REPORT COMPLETED")
        logger.info(f"📊 Report period: {report['week_start']} to {report['week_end']}")
        logger.info("=" * 80)

    except Exception as e:
        logger.error("=" * 80)
        logger.error(f"❌ WEEKLY REPORT FAILED: {e}")
        logger.error("=" * 80)


# Scheduler para relatório semanal (domingos 23h)
async def weekly_report_scheduler():
    """
    Background task para executar relatório semanal aos domingos

    Roda em loop infinito, checando a cada hora se é domingo 23h
    """
    while True:
        try:
            now = datetime.now(timezone.utc)

            # Converter para horário de São Paulo (UTC-3)
            sao_paulo_tz = timezone(timedelta(hours=-3))
            now_sp = now.astimezone(sao_paulo_tz)

            # Checar se é domingo (weekday() == 6) e hora >= 23h
            if now_sp.weekday() == 6 and now_sp.hour >= 23:
                logger.info("🗓️ Sunday night detected - running weekly report...")
                await run_weekly_report_job()

                # Dormir até segunda-feira para não executar novamente
                await asyncio.sleep(86400)  # 24 horas

            else:
                # Checar novamente em 1 hora
                logger.debug(f"⏰ Weekly report check: Not Sunday 23h yet ({now_sp.isoformat()})")
                await asyncio.sleep(3600)  # 1 hora

        except Exception as e:
            logger.error(f"❌ Weekly scheduler error: {e}")
            await asyncio.sleep(3600)  # Tentar novamente em 1 hora

                logger.error("=" * 80)
                logger.error("❌ ALL API KEYS EXHAUSTED - STOPPING COLLECTION")
                logger.error(f"✅ Collected {canais_sucesso}/{total_canais} canais")
                logger.error(f"📊 Total requests used: {collector.total_quota_units}")
                logger.error("=" * 80)
                break
            
            try:
                logger.info(f"[{index}/{total_canais}] 🔄 Processing: {canal['nome_canal']}")
                
                canal_data = await collector.get_canal_data(canal['url_canal'], canal['nome_canal'])
                if canal_data:
                    saved = await db.save_canal_data(canal['id'], canal_data)
                    if saved:
                        canais_sucesso += 1
                        logger.info(f"✅ [{index}/{total_canais}] Success: {canal['nome_canal']}")
                    else:
                        canais_erro += 1
                        logger.warning(f"⚠️ [{index}/{total_canais}] Data not saved (all zeros): {canal['nome_canal']}")
                else:
                    canais_erro += 1
                    logger.warning(f"❌ [{index}/{total_canais}] Failed: {canal['nome_canal']}")
                
                videos_data = await collector.get_videos_data(canal['url_canal'], canal['nome_canal'])
                if videos_data:
                    await db.save_videos_data(canal['id'], videos_data)
                    videos_total += len(videos_data)
                
                await db.update_last_collection(canal['id'])
                
                await asyncio.sleep(1)
                
            except Exception as e:
                logger.error(f"❌ Error processing {canal['nome_canal']}: {e}")
                canais_erro += 1
                continue
        
        stats = collector.get_request_stats()
        total_requests = stats['total_quota_units']
        
        logger.info("=" * 80)
        logger.info(f"📊 COLLECTION STATISTICS")
        logger.info(f"✅ Success: {canais_sucesso}/{total_canais}")
        logger.info(f"❌ Errors: {canais_erro}/{total_canais}")
        logger.info(f"🎬 Videos: {videos_total}")
        logger.info(f"📡 Total API Requests: {total_requests}")
        logger.info(f"🔑 Active keys: {stats['active_keys']}/{len(collector.api_keys)}")
        logger.info("=" * 80)
        
        if canais_sucesso > 0:
            try:
                logger.info("=" * 80)
                logger.info("🔔 CHECKING NOTIFICATIONS")
                logger.info("=" * 80)
                await notifier.check_and_create_notifications()
                logger.info("✅ Notification check completed")
            except Exception as e:
                logger.error(f"❌ Error checking notifications: {e}")
        
        if canais_sucesso >= (total_canais * 0.5):
            logger.info("🧹 Cleanup threshold met (>50% success)")
            await db.cleanup_old_data()
        else:
            logger.warning(f"⏭️ Skipping cleanup - only {canais_sucesso}/{total_canais} succeeded")
        
        if canais_erro == 0:
            status = "sucesso"
        elif canais_sucesso > 0:
            status = "parcial"
        else:
            status = "erro"
        
        if coleta_id:
            await db.update_coleta_log(
                coleta_id=coleta_id,
                status=status,
                canais_sucesso=canais_sucesso,
                canais_erro=canais_erro,
                videos_coletados=videos_total,
                requisicoes_usadas=total_requests
            )
        
        logger.info("=" * 80)
        logger.info(f"✅ COLLECTION COMPLETED")
        logger.info("=" * 80)
        
        last_collection_time = datetime.now(timezone.utc)
n        # Run daily analysis after collection
        await run_daily_analysis_job()
        
    except Exception as e:
        logger.error("=" * 80)
        logger.error(f"❌ COLLECTION JOB FAILED: {e}")
        logger.error("=" * 80)
        
        if coleta_id:
            await db.update_coleta_log(
                coleta_id=coleta_id,
                status="erro",
                canais_sucesso=canais_sucesso,
                canais_erro=canais_erro,
                videos_coletados=videos_total,
                requisicoes_usadas=collector.total_quota_units if hasattr(collector, 'total_quota_units') else 0,
                mensagem_erro=str(e)
            )
        
        raise
    finally:
        collection_in_progress = False

@app.on_event("startup")
async def startup_event():
    logger.info("=" * 80)
    logger.info("🚀 YOUTUBE DASHBOARD API STARTING")
    logger.info("=" * 80)
    
    try:
        await db.test_connection()
        logger.info("✅ Database connected")
    except Exception as e:
        logger.error(f"❌ Database failed: {e}")
    
    try:
        await db.cleanup_stuck_collections()
    except Exception as e:
        logger.error(f"Error cleaning stuck collections: {e}")
    
    asyncio.create_task(weekly_report_scheduler())
    logger.info("📅 Scheduling daily collection (NO startup collection)")
    asyncio.create_task(schedule_daily_collection())
    logger.info("=" * 80)

async def schedule_daily_collection():
    logger.info("=" * 80)
    logger.info("⏰ PROTEÇÃO DE STARTUP ATIVADA")
    logger.info("⏳ Aguardando 5 minutos para evitar coletas durante deploy...")
    logger.info("=" * 80)
    await asyncio.sleep(300)
    logger.info("✅ Proteção de startup completa - scheduler ativo")
    
    while True:
        try:
            now = datetime.now(timezone.utc)
            
            next_run = now.replace(hour=8, minute=0, second=0, microsecond=0)
            
            if next_run <= now:
                next_run += timedelta(days=1)
            
            sleep_seconds = (next_run - now).total_seconds()
            
            logger.info("=" * 80)
            logger.info(f"⏰ Next collection: {next_run.isoformat()} (05:00 AM São Paulo)")
            logger.info(f"⏳ Sleeping for {sleep_seconds/3600:.1f} hours")
            logger.info("=" * 80)
            
            await asyncio.sleep(sleep_seconds)
            
            can_collect, message = await can_start_collection()
            
            if can_collect:
                logger.info("🚀 Starting scheduled collection...")
                await run_collection_job()
            else:
                logger.warning(f"⚠️ Scheduled collection blocked: {message}")
            
        except Exception as e:
            logger.error(f"❌ Scheduled collection failed: {e}")
            await asyncio.sleep(3600)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
