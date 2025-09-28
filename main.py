# main.py - versão corrigida
from fastapi import FastAPI, HTTPException, BackgroundTasks, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import uvicorn
import os
from datetime import datetime, timedelta
from typing import Optional, List
import asyncio
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = FastAPI(title="YouTube Dashboard API", version="1.0.0")

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Em produção, especifique domínios
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize services with error handling
try:
    from database import SupabaseClient
    from collector import YouTubeCollector
    
    db = SupabaseClient()
    collector = YouTubeCollector()
    services_initialized = True
    logger.info("Services initialized successfully")
except Exception as e:
    logger.error(f"Failed to initialize services: {e}")
    services_initialized = False
    db = None
    collector = None

@app.get("/")
async def root():
    return {
        "message": "YouTube Dashboard API",
        "version": "1.0.0",
        "status": "running",
        "services": services_initialized
    }

@app.get("/health")
async def health_check():
    """Health check endpoint - simplified version"""
    health_status = {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "services": {
            "api": "running",
            "supabase": "unknown",
            "youtube": "unknown"
        }
    }
    
    # Only test connections if services are initialized
    if services_initialized and db:
        try:
            # Quick test without throwing errors
            await asyncio.wait_for(db.test_connection(), timeout=5.0)
            health_status["services"]["supabase"] = "connected"
        except:
            health_status["services"]["supabase"] = "disconnected"
    
    if collector:
        health_status["services"]["youtube"] = "configured"
    
    return health_status

@app.get("/api/canais")
async def get_canais(
    nicho: Optional[str] = Query(None),
    subnicho: Optional[str] = Query(None),
    views_60d_min: Optional[int] = Query(None),
    views_30d_min: Optional[int] = Query(None),
    views_15d_min: Optional[int] = Query(None),
    views_7d_min: Optional[int] = Query(None),
    score_min: Optional[float] = Query(None),
    growth_min: Optional[float] = Query(None),
    limit: int = Query(100, le=500),
    offset: int = Query(0, ge=0)
):
    """Get canais with filters for Funcionalidade 1"""
    if not services_initialized or not db:
        raise HTTPException(status_code=503, detail="Service temporarily unavailable")
    
    try:
        canais = await db.get_canais_with_filters(
            nicho=nicho,
            subnicho=subnicho,
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

@app.get("/api/videos")
async def get_videos(
    nicho: Optional[str] = Query(None),
    subnicho: Optional[str] = Query(None),
    canal: Optional[str] = Query(None),
    periodo_publicacao: str = Query("60d", regex="^(60d|30d|15d|7d)$"),
    views_min: Optional[int] = Query(None),
    growth_min: Optional[float] = Query(None),
    order_by: str = Query("views_atuais", regex="^(views_atuais|growth_video|data_publicacao)$"),
    limit: int = Query(100, le=500),
    offset: int = Query(0, ge=0)
):
    """Get videos with filters for Funcionalidade 2"""
    if not services_initialized or not db:
        raise HTTPException(status_code=503, detail="Service temporarily unavailable")
    
    try:
        videos = await db.get_videos_with_filters(
            nicho=nicho,
            subnicho=subnicho,
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
    """Get available filter options"""
    if not services_initialized or not db:
        raise HTTPException(status_code=503, detail="Service temporarily unavailable")
    
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
    status: str = "ativo"
):
    """Add a canal manually"""
    if not services_initialized or not db:
        raise HTTPException(status_code=503, detail="Service temporarily unavailable")
    
    try:
        canal_data = {
            'nome_canal': nome_canal,
            'url_canal': url_canal,
            'nicho': nicho,
            'subnicho': subnicho,
            'status': status
        }
        
        result = await db.upsert_canal(canal_data)
        return {"message": "Canal added successfully", "canal": result}
    except Exception as e:
        logger.error(f"Error adding canal: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/collect-data")
async def trigger_collection(background_tasks: BackgroundTasks):
    """Trigger data collection manually"""
    if not services_initialized or not db or not collector:
        raise HTTPException(status_code=503, detail="Service temporarily unavailable")
    
    try:
        background_tasks.add_task(run_collection_job)
        return {"message": "Collection started", "status": "processing"}
    except Exception as e:
        logger.error(f"Error starting collection: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/stats")
async def get_stats():
    """Get system statistics"""
    if not services_initialized or not db:
        return {
            "total_canais": 0,
            "total_videos": 0,
            "last_collection": None,
            "system_status": "initializing"
        }
    
    try:
        stats = await db.get_system_stats()
        return stats
    except Exception as e:
        logger.error(f"Error fetching stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Background task
async def run_collection_job():
    """Run the collection job"""
    if not db or not collector:
        logger.error("Cannot run collection - services not initialized")
        return
    
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

# Startup event
@app.on_event("startup")
async def startup_event():
    """Initialize on startup"""
    logger.info("Starting YouTube Dashboard API...")
    
    if services_initialized:
        # Schedule daily collection
        asyncio.create_task(schedule_daily_collection())
        logger.info("Daily collection scheduled")
    else:
        logger.warning("Services not fully initialized - running in limited mode")

async def schedule_daily_collection():
    """Schedule daily collection job at 6 AM"""
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
            await run_collection_job()
            
        except Exception as e:
            logger.error(f"Scheduled collection failed: {e}")
            await asyncio.sleep(3600)  # Retry in 1 hour

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
