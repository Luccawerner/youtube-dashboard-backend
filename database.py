async def run_collection_job():
    coleta_id = None
    canais_sucesso = 0
    canais_erro = 0
    videos_total = 0
    
    try:
        logger.info("Starting collection job...")
        
        canais_to_collect = await db.get_canais_for_collection()
        total_canais = len(canais_to_collect)
        logger.info(f"Found {total_canais} canais to collect")
        
        coleta_id = await db.create_coleta_log(total_canais)
        
        for canal in canais_to_collect:
            try:
                logger.info(f"Collecting data for canal: {canal['nome_canal']}")
                
                canal_data = await collector.get_canal_data(canal['url_canal'])
                if canal_data:
                    saved = await db.save_canal_data(canal['id'], canal_data)
                    if saved:
                        canais_sucesso += 1
                    else:
                        canais_erro += 1
                        logger.warning(f"Data not saved for {canal['nome_canal']} (likely all zeros)")
                else:
                    canais_erro += 1
                    logger.warning(f"No data collected for canal {canal['nome_canal']}")
                
                videos_data = await collector.get_videos_data(canal['url_canal'])
                if videos_data:
                    await db.save_videos_data(canal['id'], videos_data)
                    videos_total += len(videos_data)
                
                await db.update_last_collection(canal['id'])
                
                await asyncio.sleep(1)
                
            except Exception as e:
                logger.error(f"Error collecting data for canal {canal['nome_canal']}: {e}")
                canais_erro += 1
                continue
        
        # Só faz cleanup se mais de 50% dos canais tiveram sucesso
        if canais_sucesso >= (total_canais * 0.5):
            await db.cleanup_old_data()
            logger.info("Cleanup executed successfully")
        else:
            logger.warning(f"Skipping cleanup - only {canais_sucesso}/{total_canais} canais succeeded")
        
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
                videos_coletados=videos_total
            )
        
        logger.info(f"Collection job completed: {canais_sucesso} success, {canais_erro} errors, {videos_total} videos")
        
    except Exception as e:
        logger.error(f"Collection job failed: {e}")
        
        if coleta_id:
            await db.update_coleta_log(
                coleta_id=coleta_id,
                status="erro",
                canais_sucesso=canais_sucesso,
                canais_erro=canais_erro,
                videos_coletados=videos_total,
                mensagem_erro=str(e)
            )
        
        raise
