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

# CORS middleware - DEVE VIR ANTES DAS ROTAS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global variables for services
db = None
collector = None
services_initialized = False

@app.get("/")
async def root():
    """Root endpoint - sempre funciona"""
    return {
        "message": "YouTube Dashboard API",
        "version": "1.0.0",
        "status": "running"
    }

@app.get("/health")
async def health_check():
    """Health check endpoint - MAIS SIMPLES POSSÍVEL"""
    return {"status": "ok"}

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
    """Get canais with filters"""
    if not services_initialized or not db:
        return {"canais": [], "total": 0, "message": "Service initializing"}
    
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
        return {"canais": [], "total": 0, "error": str(e)}

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
    """Get videos with filters"""
    if not services_initialized or not db:
        return {"videos": [], "total": 0, "message": "Service initializing"}
    
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
        return {"videos": [], "total": 0, "error": str(e)}

@app.get("/api/filtros")
async def get_filtros():
    """Get filter options"""
    if not services_initialized or not db:
        return {"nichos": [], "subnichos": [], "canais": []}
    
    try:
        filtros = await db.get_filter_options()
        return filtros
    except Exception as e:
        logger.error(f"Error fetching filtros: {e}")
        return {"nichos": [], "subnichos": [], "canais": []}

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
        raise HTTPException(status_code=503, detail="Service not ready")
    
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
        raise HTTPException(status_code=503, detail="Service not ready")
    
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
            "total_videos_30d": 0,
            "last_collection": None,
            "system_status": "initializing"
        }
    
    try:
        stats = await db.get_system_stats()
        return stats
    except Exception as e:
        logger.error(f"Error fetching stats: {e}")
        return {
            "total_canais": 0,
            "total_videos_30d": 0,
            "last_collection": None,
            "system_status": "error",
            "error": str(e)
        }

async def run_collection_job():
    """Run collection job"""
    global db, collector
    
    if not db or not collector:
        logger.error("Cannot run collection - services not initialized")
        return
    
    try:
        logger.info("Starting collection job...")
        
        canais_to_collect = await db.get_canais_for_collection()
        logger.info(f"Found {len(canais_to_collect)} canais to collect")
        
        for canal in canais_to_collect:
            try:
                logger.info(f"Collecting data for canal: {canal['nome_canal']}")
                
                canal_data = await collector.get_canal_data(canal['url_canal'])
                if canal_data:
                    await db.save_canal_data(canal['id'], canal_data)
                
                videos_data = await collector.get_videos_data(canal['url_canal'])
                if videos_data:
                    await db.save_videos_data(canal['id'], videos_data)
                
                await db.update_last_collection(canal['id'])
                await asyncio.sleep(1)
                
            except Exception as e:
                logger.error(f"Error collecting data for canal {canal['nome_canal']}: {e}")
                continue
        
        await db.cleanup_old_data()
        logger.info("Collection job completed")
    except Exception as e:
        logger.error(f"Collection job failed: {e}")

async def schedule_daily_collection():
    """Schedule daily collection job"""
    while True:
        try:
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
            await asyncio.sleep(3600)

async def initialize_services():
    """Initialize services in background"""
    global db, collector, services_initialized
    
    await asyncio.sleep(1)  # Small delay to ensure server is ready
    
    try:
        from database import SupabaseClient
        from collector import YouTubeCollector
        
        db = SupabaseClient()
        collector = YouTubeCollector()
        
        # Test database connection
        await db.test_connection()
        
        services_initialized = True
        logger.info("All services initialized successfully")
        
        # Start scheduled collection
        asyncio.create_task(schedule_daily_collection())
        
    except Exception as e:
        logger.error(f"Failed to initialize services: {e}")
        services_initialized = False

@app.on_event("startup")
async def startup_event():
    """Startup event - initialize services in background"""
    logger.info("Starting YouTube Dashboard API...")
    # Initialize services in background to not block startup
    asyncio.create_task(initialize_services())

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
