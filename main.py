from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import uvicorn
import os
from datetime import datetime, timedelta
from typing import Optional, List
import asyncio
import logging

from database import SupabaseClient
from collector import YouTubeCollector

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="YouTube Dashboard API", version="1.0.0")

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize services
db = SupabaseClient()
collector = YouTubeCollector()

@app.get("/")
async def root():
    return {"message": "YouTube Dashboard API is running", "status": "healthy", "version": "1.0"}

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    try:
        # Test database connection
        await db.test_connection()
        return {
            "status": "healthy", 
            "timestamp": datetime.now().isoformat(),
            "supabase": "connected",
            "youtube_api": "configured",
            "sheets": "temporarily_disabled"
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
    views_60d_min: Optional[int] = None,
    views_30d_min: Optional[int] = None,
    views_15d_min: Optional[int] = None,
    views_7d_min: Optional[int] = None,
    score_min: Optional[float] = None,
    growth_min: Optional[float] = None,
    limit: Optional[int] = 100,
    offset: Optional[int] = 0
):
    """
    Get canais with filters for Funcionalidade 1
    """
    try:
        canais = await db.get_canais_with_filters(
            nicho=nicho,
            subnicho=subnicho,
            lingua=lingua,
            tipo=tipo,
            views_60d_min=views_60d_min,
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
    views_60d_min: Optional[int] = None,
    views_30d_min: Optional[int] = None,
    views_15d_min: Optional[int] = None,
    views_7d_min: Optional[int] = None,
    score_min: Optional[float] = None,
    growth_min: Optional[float] = None,
    limit: Optional[int] = 100,
    offset: Optional[int] = 0
):
    """
    Get APENAS nossos canais (tipo='nosso')
    """
    try:
        canais = await db.get_canais_with_filters(
            nicho=nicho,
            subnicho=subnicho,
            lingua=lingua,
            tipo="nosso",
            views_60d_min=views_60d_min,
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
    offset: Optional[int] = 0
):
    """
    Get videos with filters for Funcionalidade 2
    """
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
    """
    Get available filter options (nichos, subnichos, canais)
    """
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
    nicho: str,
    subnicho: str = "",
    lingua: str = "English",
    tipo: str = "minerado",
    status: str = "ativo"
):
    """
    Add a canal manually
    """
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

@app.post("/api/collect-data")
async def collect_data(background_tasks: BackgroundTasks):
    """
    Trigger data collection manually
    """
    try:
        background_tasks.add_task(run_collection_job)
        return {"message": "Collection started", "status": "processing"}
    except Exception as e:
        logger.error(f"Error starting collection: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/stats")
async def get_stats():
    """
    Get system statistics
    """
    try:
        stats = await db.get_system_stats()
        return stats
    except Exception as e:
        logger.error(f"Error fetching stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/cleanup")
async def cleanup_data():
    """
    Limpar dados com mais de 60 dias manualmente
    """
    try:
        await db.cleanup_old_data()
        return {"message": "Cleanup concluído com sucesso", "status": "success"}
    except Exception as e:
        logger.error(f"Error in cleanup: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ========================
# FAVORITOS - ENDPOINTS
# ========================

@app.post("/api/favoritos/adicionar")
async def add_favorito(tipo: str, item_id: int):
    """
    Add item to favorites
    tipo: 'canal' ou 'video'
    item_id: ID do canal ou vídeo
    """
    try:
        logger.info(f"Tentando adicionar favorito: tipo={tipo}, item_id={item_id}")
        
        if tipo not in ["canal", "video"]:
            raise HTTPException(status_code=400, detail="Tipo deve ser 'canal' ou 'video'")
        
        # Verificar se o item existe antes de adicionar
        if tipo == "canal":
            canal_exists = db.supabase.table("canais_monitorados").select("id").eq("id", item_id).execute()
            if not canal_exists.data:
                logger.error(f"Canal {item_id} não encontrado")
                raise HTTPException(status_code=404, detail="Canal não encontrado")
        elif tipo == "video":
            video_exists = db.supabase.table("videos_historico").select("id").eq("id", item_id).execute()
            if not video_exists.data:
                logger.error(f"Video {item_id} não encontrado")
                raise HTTPException(status_code=404, detail="Vídeo não encontrado")
        
        result = await db.add_favorito(tipo, item_id)
        logger.info(f"Favorito adicionado com sucesso: {result}")
        return {"message": "Favorito adicionado com sucesso", "favorito": result}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error adding favorito: {e}")
        logger.error(f"Tipo: {tipo}, Item ID: {item_id}")
        raise HTTPException(status_code=500, detail=f"Erro ao adicionar favorito: {str(e)}")

@app.delete("/api/favoritos/remover")
async def remove_favorito(tipo: str, item_id: int):
    """
    Remove item from favorites
    tipo: 'canal' ou 'video'
    item_id: ID do canal ou vídeo
    """
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
    """
    Get all favorited channels
    """
    try:
        canais = await db.get_favoritos_canais()
        return {"canais": canais, "total": len(canais)}
    except Exception as e:
        logger.error(f"Error fetching favoritos canais: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/favoritos/videos")
async def get_favoritos_videos():
    """
    Get all favorited videos
    """
    try:
        videos = await db.get_favoritos_videos()
        return {"videos": videos, "total": len(videos)}
    except Exception as e:
        logger.error(f"Error fetching favoritos videos: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ========================
# DELETE CANAL - ENDPOINT
# ========================

@app.delete("/api/canais/{canal_id}")
async def delete_canal(canal_id: int, permanent: bool = False):
    """
    Delete or deactivate a canal
    permanent=False: marca como inativo
    permanent=True: deleta permanentemente
    """
    try:
        if permanent:
            await db.delete_canal_permanently(canal_id)
            return {"message": "Canal deletado permanentemente"}
        else:
            # Just mark as inactive
            response = db.supabase.table("canais_monitorados").update({
                "status": "inativo"
            }).eq("id", canal_id).execute()
            return {"message": "Canal desativado", "canal": response.data}
    except Exception as e:
        logger.error(f"Error deleting canal: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Background tasks
async def run_collection_job():
    """Run the hybrid collection job"""
    try:
        logger.info("Starting collection job...")
        
        # Get canais that need collection
        canais_to_collect = await db.get_canais_for_collection()
        logger.info(f"Found {len(canais_to_collect)} canais to collect")
        
        for canal in canais_to_collect:
            try:
                logger.info(f"Collecting data for canal: {canal['nome_canal']}")
                
                # Collect canal data
                canal_data = await collector.get_canal_data(canal['url_canal'])
                if canal_data:
                    await db.save_canal_data(canal['id'], canal_data)
                
                # Collect videos data
                videos_data = await collector.get_videos_data(canal['url_canal'])
                if videos_data:
                    await db.save_videos_data(canal['id'], videos_data)
                
                # Update last collection timestamp
                await db.update_last_collection(canal['id'])
                
                # Small delay to avoid rate limiting
                await asyncio.sleep(1)
                
            except Exception as e:
                logger.error(f"Error collecting data for canal {canal['nome_canal']}: {e}")
                continue
        
        # Cleanup old data
        await db.cleanup_old_data()
        
        logger.info("Collection job completed")
    except Exception as e:
        logger.error(f"Collection job failed: {e}")
        raise

# Startup events
@app.on_event("startup")
async def startup_event():
    """Initialize services on startup"""
    logger.info("Starting YouTube Dashboard API...")
    
    # Test connections
    try:
        await db.test_connection()
        logger.info("Database connection successful")
    except Exception as e:
        logger.error(f"Database connection failed: {e}")
    
    # Schedule daily collection job
    asyncio.create_task(schedule_daily_collection())

async def schedule_daily_collection():
    """Schedule daily collection job"""
    while True:
        try:
            # Calculate time until next 6 AM
            now = datetime.now()
            next_run = now.replace(hour=6, minute=0, second=0, microsecond=0)
            if next_run <= now:
                next_run += timedelta(days=1)
            
            sleep_seconds = (next_run - now).total_seconds()
            logger.info(f"Next collection scheduled for {next_run}")
            
            await asyncio.sleep(sleep_seconds)
            
            # Run collection
            await run_collection_job()
            
        except Exception as e:
            logger.error(f"Scheduled collection failed: {e}")
            # Sleep 1 hour before retrying
            await asyncio.sleep(3600)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
