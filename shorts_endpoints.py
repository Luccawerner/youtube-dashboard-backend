"""
Shorts Production API Endpoints.

Endpoints para o dashboard Shorts Factory:
- Sugerir temas (GPT-4 Mini)
- Gerar produção (Roteirista + Diretor via Claude CLI)
- Executar Freepik (Playwright)
- Editar com Remotion (Whisper + legendas + Drive upload)
- Produzir tudo (1 clique: Freepik → Remotion → Drive)
- Logs em tempo real
- CRUD de produções (via Supabase)
"""

import logging
import json
import os
import time
from datetime import datetime
from collections import defaultdict
from fastapi import APIRouter, HTTPException, BackgroundTasks, Body
from pydantic import BaseModel
from typing import Optional
from database import SupabaseClient

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/shorts", tags=["shorts"])

db = SupabaseClient()

# === Sistema de logs em tempo real (in-memory) ===
_production_logs: dict[int, list[dict]] = defaultdict(list)
_production_status: dict[int, str] = {}  # "idle" | "running" | "done" | "error"


def _add_log(producao_id: int, msg: str):
    """Adiciona log pra uma produção."""
    entry = {"time": datetime.now().strftime("%H:%M:%S"), "msg": msg}
    _production_logs[producao_id].append(entry)
    try:
        logger.info(f"[shorts][{producao_id}] {msg}")
    except UnicodeEncodeError:
        logger.info(f"[shorts][{producao_id}] {msg.encode('ascii', 'replace').decode()}")


def _log_callback(producao_id: int):
    """Retorna callback pra usar no pipeline."""
    return lambda msg: _add_log(producao_id, msg)


# === Models ===

class GerarRequest(BaseModel):
    topic: str
    canal: str
    canal_id: Optional[int] = None
    subnicho: str
    lingua: str
    avulso: bool = False
    tom: Optional[str] = None
    formato: Optional[str] = None
    video_ref: Optional[str] = None
    video_ref_titulo: Optional[str] = None


class SugerirTemasRequest(BaseModel):
    canal: str = ""
    subnicho: str = ""
    lingua: str = "Português"
    tema_livre: str = ""


# === Background tasks ===

def _run_production_bg(topic: str, canal: str, canal_id: int | None, subnicho: str, lingua: str,
                       tom: str = "", formato: str = "livre", video_ref: str = "",
                       video_ref_titulo: str = ""):
    """Roda o pipeline de geração em background com analista + planilha."""
    try:
        topic_safe = topic.encode('ascii', 'replace').decode()
        canal_safe = canal.encode('ascii', 'replace').decode()
        logger.info(f"[shorts] BG: Iniciando producao '{topic_safe}' para {canal_safe} (tom={tom}, formato={formato})")

        from _features.shorts_production.pipeline import run_production
        result = run_production(
            topic, canal, canal_id or 0, subnicho, lingua,
            tom=tom, formato=formato, video_ref=video_ref, video_ref_titulo=video_ref_titulo,
        )

        # Escrever na planilha de shorts
        sheets_row_num = None
        try:
            from _features.shorts_production.sheets_writer import write_production_to_sheet
            pj = result.get("producao_json", {})
            cenas = pj.get("cenas", [])
            prompts_img = "\n".join(c.get("prompt_imagem", "") for c in cenas)
            prompts_anim = "\n".join(c.get("prompt_animacao", "") for c in cenas)

            sheets_row_num = write_production_to_sheet(canal, subnicho, {
                "data": datetime.utcnow().strftime("%d/%m/%Y"),
                "tom": tom or "-",
                "titulo": result.get("titulo", ""),
                "descricao": pj.get("descricao", ""),
                "script": pj.get("script", ""),
                "prompts_imagem": prompts_img,
                "prompts_animacao": prompts_anim,
                "formato": formato,
                "video_ref": video_ref or "",
            })
            logger.info(f"[shorts] BG: Planilha atualizada, linha {sheets_row_num}")
        except Exception as sheet_err:
            logger.warning(f"[shorts] BG: Erro ao escrever planilha: {str(sheet_err)[:100]}")

        insert_data = {
            "canal": result["canal"],
            "subnicho": result["subnicho"],
            "lingua": result["lingua"],
            "titulo": result["titulo"],
            "tom": tom,
            "formato": formato,
            "video_ref": video_ref,
            "sheets_row_num": sheets_row_num,
            "producao_json": result["producao_json"],
            "drive_link": result["drive_link"],
            "status": "producao",
        }
        if canal_id:
            insert_data["canal_id"] = canal_id
        db.supabase.table("shorts_production").insert(insert_data).execute()

        titulo_safe = result['titulo'].encode('ascii', 'replace').decode()
        logger.info(f"[shorts] BG: Producao salva: {titulo_safe}")
    except Exception as e:
        import traceback
        logger.error(f"[shorts] BG ERRO: {str(e).encode('ascii', 'replace').decode()}")
        logger.error(traceback.format_exc())


def _run_freepik_bg(producao_id: int, json_path: str):
    """Roda automação do Freepik em background com logs."""
    _production_status[producao_id] = "running"
    _production_logs[producao_id] = []
    _add_log(producao_id, "Iniciando Freepik Spaces...")

    try:
        from _features.shorts_production.freepik_automation import run_freepik_production
        success = run_freepik_production(json_path, log_callback=_log_callback(producao_id))

        if success:
            db.supabase.table("shorts_production").update({
                "status": "edicao",
                "updated_at": datetime.utcnow().isoformat(),
            }).eq("id", producao_id).execute()
            _add_log(producao_id, "Freepik concluido! Status >> edicao")
            _production_status[producao_id] = "done"
        else:
            _add_log(producao_id, "ERRO: Freepik falhou")
            _production_status[producao_id] = "error"
    except Exception as e:
        _add_log(producao_id, f"ERRO: {str(e)[:200]}")
        _production_status[producao_id] = "error"


def _update_sheet_drive_link(producao_id: int, drive_url: str):
    """Atualiza Link Drive na planilha de shorts (se tiver row_num salvo)."""
    for attempt in range(2):
        try:
            prod = db.supabase.table("shorts_production").select(
                "canal, subnicho, sheets_row_num"
            ).eq("id", producao_id).single().execute()
            if prod.data and prod.data.get("sheets_row_num"):
                from _features.shorts_production.sheets_writer import update_drive_link
                update_drive_link(
                    prod.data["canal"], prod.data["subnicho"], prod.data["sheets_row_num"], drive_url
                )
                logger.info(f"[shorts] Planilha: Drive link atualizado pra producao {producao_id} (linha {prod.data['sheets_row_num']})")
                return
            else:
                logger.warning(f"[shorts] Planilha: producao {producao_id} sem sheets_row_num")
                return
        except Exception as e:
            logger.warning(f"[shorts] Planilha: Erro ao atualizar Drive link (tentativa {attempt+1}): {str(e)[:100]}")
            if attempt == 0:
                import time
                time.sleep(5)


def _update_sheet_upload_status(producao_id: int, youtube_video_id: str):
    """Atualiza Upload status na planilha de shorts (se tiver row_num salvo)."""
    try:
        prod = db.supabase.table("shorts_production").select(
            "canal, subnicho, sheets_row_num"
        ).eq("id", producao_id).single().execute()
        if prod.data and prod.data.get("sheets_row_num"):
            from _features.shorts_production.sheets_writer import update_upload_status
            update_upload_status(
                prod.data["canal"], prod.data["subnicho"], prod.data["sheets_row_num"],
                "\u2705"
            )
            logger.info(f"[shorts] Planilha: Upload status atualizado pra producao {producao_id}")
    except Exception as e:
        logger.warning(f"[shorts] Planilha: Erro ao atualizar Upload: {str(e)[:100]}")


def _run_editing_bg(producao_id: int, production_path: str, subnicho: str):
    """Roda Remotion + Drive em background com logs."""
    _production_status[producao_id] = "running"
    _production_logs[producao_id] = []
    _add_log(producao_id, "Iniciando edicao (Remotion + Drive)...")

    try:
        from _features.shorts_production.remotion_editor import edit_short
        result = edit_short(production_path, subnicho=subnicho, log_callback=_log_callback(producao_id))

        update_data = {
            "status": "pronto",
            "updated_at": datetime.utcnow().isoformat(),
        }
        drive_url = ""
        if isinstance(result, dict) and result.get("drive_url"):
            update_data["drive_url"] = result["drive_url"]
            drive_url = result["drive_url"]

        # Se Drive URL vazio, tentar upload manual
        if not drive_url:
            _add_log(producao_id, "Drive URL vazio. Tentando upload manual...")
            try:
                from _features.shorts_production.drive_uploader import upload_to_drive
                lingua = db.supabase.table("shorts_production").select("lingua").eq("id", producao_id).single().execute()
                lingua_val = lingua.data.get("lingua", "") if lingua.data else ""
                canal_label = f"({lingua_val[:2].upper()}) {production_path.split(os.sep)[-3].split(') ')[-1]}" if lingua_val else ""
                titulo_short = production_path.split(os.sep)[-1][:40]
                drive_url = upload_to_drive(production_path, subnicho, canal_label, titulo_short, log_callback=_log_callback(producao_id))
                if drive_url:
                    update_data["drive_url"] = drive_url
                    _add_log(producao_id, f"Drive upload manual OK")
            except Exception as drive_err:
                _add_log(producao_id, f"Drive upload manual falhou: {str(drive_err)[:100]}")

        db.supabase.table("shorts_production").update(update_data).eq("id", producao_id).execute()

        # Atualizar planilha com Drive link
        if drive_url:
            _update_sheet_drive_link(producao_id, drive_url)

        _add_log(producao_id, f"Video pronto!")
        _production_status[producao_id] = "done"
    except Exception as e:
        _add_log(producao_id, f"ERRO: {str(e)[:200]}")
        _production_status[producao_id] = "error"


def _run_full_production_bg(producao_id: int, json_path: str, production_path: str, subnicho: str):
    """Roda Freepik + Remotion + Drive em sequência."""
    _production_status[producao_id] = "running"
    _production_logs[producao_id] = []
    log = _log_callback(producao_id)

    try:
        # FASE 1: Freepik
        log("=== FASE 1: Freepik Spaces ===")
        from _features.shorts_production.freepik_automation import run_freepik_production
        success = run_freepik_production(json_path, log_callback=log)

        if not success:
            log("ERRO: Freepik falhou. Abortando.")
            _production_status[producao_id] = "error"
            return

        db.supabase.table("shorts_production").update({
            "status": "edicao",
            "updated_at": datetime.utcnow().isoformat(),
        }).eq("id", producao_id).execute()
        log("Freepik concluido! Status >> edicao")

        # FASE 2: Remotion + Drive
        log("=== FASE 2: Remotion + Drive ===")
        from _features.shorts_production.remotion_editor import edit_short
        result = edit_short(production_path, subnicho=subnicho, log_callback=log)

        update_data = {
            "status": "pronto",
            "updated_at": datetime.utcnow().isoformat(),
        }
        drive_url = ""
        if isinstance(result, dict) and result.get("drive_url"):
            update_data["drive_url"] = result["drive_url"]
            drive_url = result["drive_url"]

        # Se Remotion terminou mas Drive falhou, tentar upload manual
        if not drive_url:
            log("Drive URL vazio. Tentando upload manual...")
            try:
                from _features.shorts_production.drive_uploader import upload_to_drive
                lingua = db.supabase.table("shorts_production").select("lingua").eq("id", producao_id).single().execute()
                lingua_val = lingua.data.get("lingua", "") if lingua.data else ""
                canal_label = f"({lingua_val[:2].upper()}) {production_path.split(os.sep)[-3].split(') ')[-1]}" if lingua_val else ""
                titulo_short = production_path.split(os.sep)[-1][:40]
                drive_url = upload_to_drive(production_path, subnicho, canal_label, titulo_short, log_callback=log)
                if drive_url:
                    update_data["drive_url"] = drive_url
                    log(f"Drive upload manual OK: {drive_url}")
            except Exception as drive_err:
                log(f"Drive upload manual falhou: {str(drive_err)[:100]}")

        db.supabase.table("shorts_production").update(update_data).eq("id", producao_id).execute()

        # Atualizar planilha com Drive link
        if drive_url:
            _update_sheet_drive_link(producao_id, drive_url)

        log(f"Video pronto! Status >> pronto")
        log("=== PRODUCAO COMPLETA ===")
        _production_status[producao_id] = "done"

    except Exception as e:
        log(f"ERRO: {str(e)[:200]}")
        _production_status[producao_id] = "error"


# === Endpoints ===

@router.post("/gerar")
async def gerar_producao(req: GerarRequest, background_tasks: BackgroundTasks):
    """Gera script + prompts em background.

    Tom/formato podem vir do request (se sugerir-temas já rodou o analista)
    ou roda o analista aqui se não vieram.
    """
    tom = req.tom or ""
    formato = req.formato or "livre"
    video_ref = req.video_ref or ""
    video_ref_titulo = req.video_ref_titulo or ""

    # Só roda analista se tom não veio no request (fallback)
    if not tom and not req.avulso:
        try:
            from _features.shorts_production.analyst import analyze_channel
            analysis = analyze_channel(req.canal, req.subnicho)
            tom = analysis.get("tom", "")
            formato = analysis.get("formato", "livre")
            video_ref = analysis.get("video_ref", "")
            video_ref_titulo = analysis.get("video_ref_titulo", "")
            logger.info(f"[shorts] Analista (fallback): tom={tom}, formato={formato}")
        except Exception as e:
            logger.warning(f"[shorts] Analista falhou, usando defaults: {str(e)[:100]}")

    background_tasks.add_task(
        _run_production_bg,
        topic=req.topic,
        canal=req.canal,
        canal_id=req.canal_id,
        subnicho=req.subnicho,
        lingua=req.lingua,
        tom=tom,
        formato=formato,
        video_ref=video_ref,
        video_ref_titulo=video_ref_titulo,
    )
    return {
        "status": "gerando",
        "message": f"Produção de '{req.topic}' iniciada em background",
        "tom": tom,
        "formato": formato,
    }


@router.post("/sugerir-temas")
async def sugerir_temas(req: SugerirTemasRequest):
    """Sugere 5 temas via GPT-4 Mini. Analista filtra temas repetidos."""
    try:
        # Rodar analista pra pegar bloqueios e formato
        analysis = {}
        if req.canal and req.canal != "Avulso" and req.subnicho:
            try:
                from _features.shorts_production.analyst import analyze_channel
                analysis = analyze_channel(req.canal, req.subnicho)
            except Exception as e:
                logger.warning(f"[shorts] Analista falhou no sugerir-temas: {str(e)[:100]}")

        from _features.shorts_production.theme_suggester import suggest_themes
        temas = suggest_themes(
            canal=req.canal,
            subnicho=req.subnicho,
            lingua=req.lingua,
            tema_livre=req.tema_livre,
            temas_bloqueados=analysis.get("temas_bloqueados", ""),
            video_ref_titulo=analysis.get("video_ref_titulo", ""),
        )
        return {
            "temas": temas,
            "tom": analysis.get("tom", ""),
            "formato": analysis.get("formato", "livre"),
            "temas_bloqueados": analysis.get("temas_bloqueados", ""),
        }
    except Exception as e:
        logger.error(f"[shorts] Erro ao sugerir temas: {e}")
        raise HTTPException(500, str(e))


@router.post("/executar-freepik/{producao_id}")
async def executar_freepik(producao_id: int, background_tasks: BackgroundTasks):
    """Executa produção no Freepik Spaces via Playwright."""
    result = db.supabase.table("shorts_production").select("*").eq("id", producao_id).single().execute()
    if not result.data:
        raise HTTPException(404, "Produção não encontrada")

    drive_link = result.data.get("drive_link", "")
    json_path = os.path.join(drive_link, "producao.json") if drive_link else ""

    if not json_path or not os.path.exists(json_path):
        raise HTTPException(400, f"producao.json não encontrado em {drive_link}")

    background_tasks.add_task(_run_freepik_bg, producao_id, json_path)
    return {"status": "executando", "message": f"Freepik iniciado para '{result.data['titulo']}'"}


@router.post("/editar/{producao_id}")
async def editar_producao(producao_id: int, background_tasks: BackgroundTasks):
    """Aciona Remotion + Drive upload em background."""
    result = db.supabase.table("shorts_production").select("*").eq("id", producao_id).single().execute()
    if not result.data:
        raise HTTPException(404, "Produção não encontrada")

    drive_link = result.data.get("drive_link", "")
    if not drive_link or not os.path.exists(drive_link):
        raise HTTPException(400, f"Pasta não encontrada: {drive_link}")

    subnicho = result.data.get("subnicho", "")
    background_tasks.add_task(_run_editing_bg, producao_id, drive_link, subnicho)
    return {"status": "editando", "message": f"Remotion iniciado para '{result.data['titulo']}'"}


@router.post("/produzir/{producao_id}")
async def produzir_completo(producao_id: int):
    """Adiciona na fila de producao (Freepik >> Remotion >> Drive)."""
    result = db.supabase.table("shorts_production").select("*").eq("id", producao_id).single().execute()
    if not result.data:
        raise HTTPException(404, "Produção não encontrada")

    drive_link = result.data.get("drive_link", "")
    json_path = os.path.join(drive_link, "producao.json") if drive_link else ""

    if not json_path or not os.path.exists(json_path):
        raise HTTPException(400, f"producao.json não encontrado em {drive_link}")

    subnicho = result.data.get("subnicho", "")
    from production_queue import enqueue
    queue_result = enqueue(producao_id, json_path, drive_link, subnicho)
    return {
        "status": "na_fila",
        "posicao": queue_result["posicao"],
        "message": f"Na fila (posição {queue_result['posicao']})",
    }


class BatchEditarRequest(BaseModel):
    mode: str = "todos"  # "subnicho", "leva", "todos"
    subnicho: Optional[str] = None
    leva: Optional[int] = None


@router.post("/batch-editar")
async def batch_editar(
    background_tasks: BackgroundTasks,
    req: Optional[BatchEditarRequest] = Body(None),
):
    """Enfileira Remotion + Drive pra shorts em status=edicao (1 por vez). Filtra por subnicho/leva."""
    req = req or BatchEditarRequest()
    query = db.supabase.table("shorts_production").select(
        "id, canal, titulo, drive_link, subnicho"
    ).eq("status", "edicao").order("created_at")

    if req.mode == "subnicho" and req.subnicho:
        query = query.eq("subnicho", req.subnicho)
    elif req.mode == "leva":
        if req.leva == 3:
            leva3_names = _get_leva3_canal_names()
            if not leva3_names:
                return {"status": "nenhum", "message": "Nenhum canal na Leva 3"}
            query = query.in_("canal", leva3_names)
        elif req.leva in (1, 2):
            subs = LEVA_1_SUBNICHOS if req.leva == 1 else LEVA_2_SUBNICHOS
            query = query.in_("subnicho", subs)

    edicoes = query.execute()

    if not edicoes.data:
        return {"status": "nenhum", "message": "Nenhum short em edicao pra esse filtro"}

    validos = []
    for p in edicoes.data:
        drive_link = p.get("drive_link", "")
        if drive_link and os.path.exists(drive_link):
            validos.append(p)

    background_tasks.add_task(_run_batch_editar_bg, validos)

    return {
        "status": "ok",
        "total": len(edicoes.data),
        "editando": len(validos),
        "message": f"{len(validos)} shorts na fila de edicao (1 por vez)",
    }


def _run_batch_editar_bg(validos: list[dict]):
    """Edita shorts 1 por vez em sequencia."""
    for i, p in enumerate(validos):
        logger.info(f"[batch-editar] {i+1}/{len(validos)}: {p['canal']}")
        try:
            _run_editing_bg(p["id"], p["drive_link"], p.get("subnicho", ""))
        except Exception as e:
            logger.error(f"[batch-editar] ERRO {p['canal']}: {str(e)[:100]}")


class BatchProduzirRequest(BaseModel):
    mode: str = "todos"  # "subnicho", "leva", "todos"
    subnicho: Optional[str] = None
    leva: Optional[int] = None


@router.post("/batch-produzir")
async def batch_produzir(req: BatchProduzirRequest, background_tasks: BackgroundTasks):
    """Enfileira shorts em status=producao pra produção. Filtra por subnicho/leva."""
    query = db.supabase.table("shorts_production").select(
        "id, canal, titulo, drive_link, subnicho"
    ).eq("status", "producao").order("created_at")

    # Filtrar por subnicho/leva
    if req.mode == "subnicho" and req.subnicho:
        query = query.eq("subnicho", req.subnicho)
    elif req.mode == "leva":
        if req.leva == 3:
            # Leva 3: filtra por NOME do canal (lista dinamica OAuth + <1000 subs)
            leva3_names = _get_leva3_canal_names()
            if not leva3_names:
                return {"status": "nenhum", "message": "Nenhum canal na Leva 3"}
            query = query.in_("canal", leva3_names)
        else:
            subs = LEVA_1_SUBNICHOS if req.leva == 1 else LEVA_2_SUBNICHOS
            query = query.in_("subnicho", subs)

    producoes = query.execute()

    if not producoes.data:
        return {"status": "nenhum", "message": "Nenhum short em producao pra enfileirar"}

    # Filtrar só os que tem producao.json no disco
    validos = []
    erros = []
    for p in producoes.data:
        drive_link = p.get("drive_link", "")
        json_path = os.path.join(drive_link, "producao.json") if drive_link else ""
        if json_path and os.path.exists(json_path):
            validos.append({**p, "json_path": json_path})
        else:
            erros.append({"id": p["id"], "canal": p["canal"], "status": "erro", "message": "producao.json nao encontrado"})

    # Enfileirar em background pra não travar o servidor
    background_tasks.add_task(_enqueue_batch_produzir, validos)

    return {
        "status": "ok",
        "total": len(producoes.data),
        "enfileirados": len(validos),
        "erros": len(erros),
        "message": f"{len(validos)} shorts sendo enfileirados, {len(erros)} sem arquivo",
    }


def _enqueue_batch_produzir(validos: list[dict]):
    """Enfileira shorts na fila de produção em background."""
    from production_queue import enqueue
    for p in validos:
        try:
            enqueue(p["id"], p["json_path"], p.get("drive_link", ""), p.get("subnicho", ""))
            logger.info(f"[batch-produzir] Enfileirado: {p['id']} ({p['canal']})")
        except Exception as e:
            logger.error(f"[batch-produzir] Erro ao enfileirar {p['id']}: {str(e)[:100]}")


@router.get("/logs/{producao_id}")
async def get_logs(producao_id: int, after: int = 0):
    """Retorna logs de uma produção (polling). after = index pra pegar só novos."""
    logs = _production_logs.get(producao_id, [])
    status = _production_status.get(producao_id, "idle")
    response = {"logs": logs[after:], "total": len(logs), "status": status}
    if status == "queued":
        from production_queue import get_position
        response["queue_position"] = get_position(producao_id)
    return response


@router.get("/fila-producao")
async def fila_producao():
    """Retorna estado da fila de producao."""
    from production_queue import get_queue_status
    return get_queue_status()


@router.delete("/fila-producao/{producao_id}")
async def remover_da_fila(producao_id: int):
    """Remove producao da fila (se ainda nao comecou)."""
    from production_queue import remove_from_queue
    removed = remove_from_queue(producao_id)
    if not removed:
        raise HTTPException(400, "Producao nao encontrada na fila ou ja em execucao")
    return {"status": "removido"}


@router.post("/pausar/{producao_id}")
async def pausar_producao(producao_id: int):
    """Pausa uma produção em andamento (marca como parado, não mata o processo)."""
    if producao_id in _production_status and _production_status[producao_id] == "running":
        _production_status[producao_id] = "paused"
        _add_log(producao_id, "PAUSADO pelo usuario")
    return {"status": "pausado"}


@router.get("/producoes")
async def listar_producoes(status: Optional[str] = None):
    """Lista produções, opcionalmente filtradas por status."""
    query = db.supabase.table("shorts_production").select("*").order("created_at", desc=True)
    if status:
        query = query.eq("status", status)
    result = query.execute()
    return {"producoes": result.data}


@router.patch("/producoes/{producao_id}/status")
async def atualizar_status(producao_id: int, status: str):
    """Atualiza status de uma produção."""
    if status not in ("producao", "edicao", "pronto", "publicado"):
        raise HTTPException(400, "Status inválido. Use: producao, edicao, pronto")

    db.supabase.table("shorts_production").update({
        "status": status,
        "updated_at": datetime.utcnow().isoformat(),
    }).eq("id", producao_id).execute()

    return {"status": "ok", "novo_status": status}


@router.delete("/producoes/{producao_id}")
async def excluir_producao(producao_id: int):
    """Exclui uma produção."""
    db.supabase.table("shorts_production").delete().eq("id", producao_id).execute()
    return {"status": "excluido"}


@router.get("/producoes/{producao_id}/json")
async def get_producao_json(producao_id: int):
    """Retorna o JSON completo de uma produção."""
    result = db.supabase.table("shorts_production").select("producao_json").eq("id", producao_id).single().execute()
    if not result.data:
        raise HTTPException(404, "Produção não encontrada")
    return result.data.get("producao_json", {})


@router.get("/edicao/fila")
async def fila_edicao():
    """Lista produções prontas pra edição."""
    result = db.supabase.table("shorts_production").select(
        "id, titulo, canal, subnicho, lingua, drive_link, created_at"
    ).eq("status", "edicao").order("created_at", desc=True).execute()
    return {"fila": result.data}


def _kill_debug_chrome_only(profile_path: str) -> int:
    """Mata apenas processos chrome.exe que usam o profile do debug (preserva Chrome pessoal).

    Usa PowerShell + Win32_Process pra filtrar pela command line.
    Retorna quantos processos foram mortos.
    """
    import subprocess
    # Escapar \ pra regex + PowerShell
    profile_pattern = profile_path.replace("\\", "\\\\")
    ps_cmd = (
        "$procs = Get-CimInstance Win32_Process -Filter \"Name='chrome.exe'\" | "
        f"Where-Object {{ $_.CommandLine -like '*{profile_path}*' }}; "
        "$procs | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }; "
        "$procs.Count"
    )
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps_cmd],
            capture_output=True, timeout=8, text=True,
        )
        out = result.stdout.strip()
        try:
            return int(out) if out.isdigit() else 0
        except Exception:
            return 0
    except Exception as e:
        logger.warning(f"[kill_debug_chrome] falhou: {e}")
        return 0


def _cdp_alive_with_freepik() -> Optional[dict]:
    """Verifica se CDP 9222 ja esta vivo e tem aba Freepik hidratada.

    Retorna dict {targetId, url, dataIds} se sim, None caso contrario.
    Considera "hidratada" se tiver >=10 elementos [data-id].
    """
    import urllib.request, json as _json
    try:
        with urllib.request.urlopen("http://localhost:9222/json/version", timeout=1.5) as r:
            _json.loads(r.read())  # so testar se responde
    except Exception:
        return None

    try:
        with urllib.request.urlopen("http://localhost:9222/json/list", timeout=2) as r:
            tabs = _json.loads(r.read())
    except Exception:
        return None

    freepik_targets = [t for t in tabs if t.get("type") == "page" and "freepik.com/pikaso/spaces" in t.get("url", "")]
    if not freepik_targets:
        return None

    # Conectar via Playwright e ver qual tem mais data-id (indicador de hidratacao)
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.connect_over_cdp("http://localhost:9222")
            best = None
            best_count = 0
            for ctx in browser.contexts:
                for pg in ctx.pages:
                    if "freepik.com/pikaso/spaces" not in pg.url:
                        continue
                    try:
                        cnt = pg.evaluate("document.querySelectorAll('[data-id]').length")
                    except Exception:
                        cnt = 0
                    if cnt > best_count:
                        try:
                            cdp = pg.context.new_cdp_session(pg)
                            info = cdp.send("Target.getTargetInfo")
                            tid = info.get("targetInfo", {}).get("targetId")
                        except Exception:
                            tid = None
                        best = {"targetId": tid, "url": pg.url, "dataIds": cnt}
                        best_count = cnt
            if best and best_count >= 10:
                return best
    except Exception as e:
        logger.warning(f"[cdp_alive_check] erro checando hidratacao: {e}")
    return None


def _cleanup_freepik_duplicates() -> dict:
    """Registra a tab Freepik correta (a mais hidratada) pro _get_page usar.

    NAO fecha pages 'duplicadas' porque em muitos casos elas sao referencias da
    MESMA tab (iframes/contexts pareados) — fechar uma derruba a outra.
    Em vez disso, identifica a que tem mais elementos [data-id] e registra seu targetId.
    O _get_page() usa esse guid pra achar exatamente essa tab.
    """
    tabs_info = {"kept_url": None, "kept_guid": None, "total_found": 0, "chosen_dataIds": 0}
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.connect_over_cdp("http://localhost:9222")
            candidates = []
            for ctx in browser.contexts:
                for pg in ctx.pages:
                    try:
                        if "freepik.com/pikaso/spaces" not in pg.url:
                            continue
                    except Exception:
                        continue
                    try:
                        cnt = pg.evaluate("document.querySelectorAll('[data-id]').length")
                    except Exception:
                        cnt = 0
                    candidates.append((pg, cnt))

            tabs_info["total_found"] = len(candidates)
            logger.info(f"[cleanup] {len(candidates)} pages Freepik: {[c[1] for c in candidates]} data-ids")

            if not candidates:
                return tabs_info

            # Ordenar por data-id count DESC, depois index DESC (ultima empate vence)
            candidates_indexed = [(pg, cnt, i) for i, (pg, cnt) in enumerate(candidates)]
            candidates_indexed.sort(key=lambda x: (x[1], x[2]), reverse=True)
            chosen = candidates_indexed[0][0]
            tabs_info["chosen_dataIds"] = candidates_indexed[0][1]

            try:
                # NAO bring_to_front: nao queremos roubar foco do usuario.
                # set_viewport_size garante render correto via CDP override.
                chosen.set_viewport_size({"width": 1920, "height": 1080})
                tabs_info["kept_url"] = chosen.url
                cdp = chosen.context.new_cdp_session(chosen)
                info = cdp.send("Target.getTargetInfo")
                tabs_info["kept_guid"] = info.get("targetInfo", {}).get("targetId")
            except Exception as e:
                logger.warning(f"[cleanup] setup tab escolhida: {e}")
    except Exception as e:
        logger.warning(f"[cleanup] falha geral: {e}")
    return tabs_info


def _save_freepik_guid(tabs_info: dict):
    if not tabs_info.get("kept_guid"):
        return
    try:
        import json as _json
        import os as _os
        with open(_os.path.join(_os.path.dirname(__file__), ".freepik_tab_guid"), "w") as f:
            _json.dump(tabs_info, f)
    except Exception:
        pass


@router.post("/inicializar-browser")
async def inicializar_browser(force: bool = False):
    """Abre Chrome debug e GARANTE 1 unica aba do Freepik Spaces.

    Otimizacoes:
      - Se Chrome debug ja esta vivo e com Freepik hidratada: pula kill/launch,
        so faz cleanup de duplicatas. Retorna em ~2-3s.
      - Preserva Chrome pessoal: mata APENAS processos que usam chrome-debug-profile.
      - Parametro force=true pula essa otimizacao e re-lança do zero.
    """
    import subprocess
    import os as _os

    chrome_path = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
    profile_path = r"C:\Users\PC\chrome-debug-profile"
    freepik_url = "https://br.freepik.com/pikaso/spaces/a166a80e-8448-4c38-b231-ce4cd2cc49ce"

    # ===== SKIP: Se Chrome debug ja ta rodando com Freepik hidratada =====
    if not force:
        existing = _cdp_alive_with_freepik()
        if existing:
            logger.info(f"[inicializar-browser] Chrome debug ja vivo com Freepik hidratada (dataIds={existing['dataIds']}), pulando relaunch")
            tabs_info = _cleanup_freepik_duplicates()
            _save_freepik_guid(tabs_info)
            return {
                "status": "ok",
                "mode": "skip_relaunch",
                "message": f"Chrome ja estava pronto. Tab com {tabs_info['chosen_dataIds']} data-ids registrada.",
                "kept_url": tabs_info["kept_url"],
                "kept_guid": tabs_info["kept_guid"],
                "total_found": tabs_info["total_found"],
            }

    # ===== KILL: So mata chrome.exe do profile debug (preserva Chrome pessoal) =====
    killed = _kill_debug_chrome_only(profile_path)
    logger.info(f"[inicializar-browser] {killed} processos chrome debug mortos (Chrome pessoal preservado)")
    if killed > 0:
        time.sleep(2)

    # Limpar session restore files (evita Chrome restaurar duplicatas)
    for session_file in ["Current Session", "Current Tabs", "Last Session", "Last Tabs"]:
        path = _os.path.join(profile_path, "Default", session_file)
        try:
            if _os.path.exists(path):
                _os.remove(path)
        except Exception:
            pass

    subprocess.Popen([
        chrome_path,
        "--remote-debugging-port=9222",
        f"--user-data-dir={profile_path}",
        "--no-first-run",
        "--no-default-browser-check",
        "--restore-last-session=false",
        "--disable-features=InfiniteSessionRestore",
        freepik_url,
    ])
    time.sleep(7)

    tabs_info = _cleanup_freepik_duplicates()
    _save_freepik_guid(tabs_info)

    return {
        "status": "ok",
        "mode": "relaunch",
        "message": f"Chrome relançado. {killed} procs debug mortos. Tab com {tabs_info['chosen_dataIds']} data-ids registrada.",
        "kept_url": tabs_info["kept_url"],
        "kept_guid": tabs_info["kept_guid"],
        "total_found": tabs_info["total_found"],
    }


@router.get("/browser-status")
async def browser_status():
    """Verifica se o Chrome com debug port está rodando."""
    import urllib.request
    try:
        resp = urllib.request.urlopen("http://127.0.0.1:9222/json/version", timeout=2)
        data = json.loads(resp.read())
        return {"connected": True, "browser": data.get("Browser", "Chrome")}
    except Exception:
        return {"connected": False}


@router.post("/upload-youtube/{producao_id}")
async def upload_youtube(producao_id: int, background_tasks: BackgroundTasks):
    """Faz upload do short pro YouTube como privado."""
    result = db.supabase.table("shorts_production").select("*").eq("id", producao_id).single().execute()
    if not result.data:
        raise HTTPException(404, "Producao nao encontrada")

    if result.data["status"] != "pronto":
        raise HTTPException(400, "Producao nao esta pronta pra upload")

    if result.data.get("youtube_video_id"):
        raise HTTPException(400, "Ja foi enviado pro YouTube")

    drive_link = result.data.get("drive_link", "")
    video_path = os.path.join(drive_link, "video_final.mp4") if drive_link else ""
    if not video_path or not os.path.exists(video_path):
        raise HTTPException(400, f"video_final.mp4 nao encontrado em {drive_link}")

    background_tasks.add_task(_run_youtube_upload_bg, producao_id, result.data, video_path)
    return {"status": "uploading", "message": f"Upload iniciado para '{result.data['titulo']}'"}


def _run_youtube_upload_bg(producao_id: int, production_data: dict, video_path: str):
    """Faz upload do short pro YouTube em background."""
    _production_status[producao_id] = "running"
    _production_logs[producao_id] = []
    log = _log_callback(producao_id)

    try:
        from dotenv import load_dotenv
        load_dotenv()

        canal = production_data.get("canal", "")
        titulo = production_data.get("titulo", "")
        log(f"Upload YouTube: {titulo}")

        # Buscar channel_id do YouTube pelo nome do canal (yt_channels)
        # Match exato primeiro, depois normalizado (sem acentos)
        canal_result = db.supabase.table("yt_channels").select(
            "channel_id"
        ).eq("channel_name", canal).eq("is_active", True).limit(1).execute()

        if not canal_result.data:
            # Match normalizado (sem acentos)
            import unicodedata
            canal_norm = unicodedata.normalize("NFD", canal).encode("ascii", "ignore").decode().lower()
            all_channels = db.supabase.table("yt_channels").select("channel_id, channel_name").eq("is_active", True).execute()
            for ch in all_channels.data:
                ch_norm = unicodedata.normalize("NFD", ch["channel_name"]).encode("ascii", "ignore").decode().lower()
                if ch_norm == canal_norm:
                    canal_result.data = [{"channel_id": ch["channel_id"]}]
                    log(f"Match normalizado: {ch['channel_name']}")
                    break

        if not canal_result.data:
            log(f"ERRO: Canal '{canal}' nao encontrado em canais_monitorados")
            _production_status[producao_id] = "error"
            return

        youtube_channel_id = canal_result.data[0]["channel_id"]
        log(f"Canal YouTube: {youtube_channel_id}")

        # Buscar metadata do producao_json
        prod_json = production_data.get("producao_json", {})
        descricao = prod_json.get("descricao", "")

        # Upload via YouTubeUploader existente
        from _features.yt_uploader.uploader import YouTubeUploader
        uploader = YouTubeUploader()

        result = uploader.upload_to_youtube(
            channel_id=youtube_channel_id,
            video_path=video_path,
            metadata={
                "titulo": titulo,
                "descricao": descricao,
            },
            skip_playlist=True,
            privacy_status="public",
        )
        log(f"Upload configurado: publico, sem playlist")

        if result.get("success"):
            video_id = result["video_id"]
            db.supabase.table("shorts_production").update({
                "youtube_video_id": video_id,
                "status": "publicado",
                "updated_at": datetime.utcnow().isoformat(),
            }).eq("id", producao_id).execute()

            # Atualizar planilha com status de upload
            _update_sheet_upload_status(producao_id, video_id)

            log(f"https://youtube.com/shorts/{video_id}")
            _production_status[producao_id] = "done"
        else:
            log(f"ERRO: Upload falhou - {result}")
            _production_status[producao_id] = "error"

    except Exception as e:
        log(f"ERRO: {str(e)[:300]}")
        _production_status[producao_id] = "error"


# === Batch Gerar ===

LEVA_1_SUBNICHOS = ["Reis Perversos", "Guerras e Civilizações", "Frentes de Guerra"]
LEVA_2_SUBNICHOS = ["Relatos de Guerra", "Monetizados", "Culturas Macabras", "Historias Sombrias"]

# Leva 3 = filtro dinamico (OAuth configurado + <LEVA3_INSCRITOS_MAX inscritos).
# NAO usa subnicho, usa lista de canais calculada em runtime.
LEVA3_INSCRITOS_MAX = 1000
_leva3_cache: dict = {"at": 0.0, "canais": []}
LEVA3_CACHE_TTL = 300  # 5 min

# Mapeamento abreviação -> nome completo da lingua
LINGUA_MAP = {
    "pt": "Português", "en": "Inglês", "es": "Espanhol", "fr": "Francês",
    "de": "Alemão", "it": "Italiano", "ja": "Japonês", "ko": "Coreano",
    "ru": "Russo", "tr": "Turco", "pl": "Polonês", "ar": "Árabe",
}


def _compute_leva3_canais() -> list[dict]:
    """Calcula dinamicamente canais da Leva 3: tem OAuth E tem <LEVA3_INSCRITOS_MAX inscritos.

    Cruza:
      - canais_monitorados (tipo=nosso, ativo) -> id interno, nome, subnicho, lingua
      - yt_channels (nome -> channel_id YouTube + is_active)
      - yt_oauth_tokens (tem token)
      - dados_canais_historico (inscritos mais recentes via canal_id interno)

    Retorna lista de dicts: [{channel_name, subnicho, lingua, inscritos}, ...]
    """
    nossos = db.supabase.table("canais_monitorados").select(
        "id, nome_canal, subnicho, lingua"
    ).eq("tipo", "nosso").eq("status", "ativo").execute().data or []

    yt = db.supabase.table("yt_channels").select(
        "channel_id, channel_name"
    ).eq("is_active", True).execute().data or []
    yt_name_to_id = {c["channel_name"]: c["channel_id"] for c in yt}

    oauth = db.supabase.table("yt_oauth_tokens").select("channel_id").execute().data or []
    oauth_ids = {r["channel_id"] for r in oauth}

    # Primeiro filtra canais com OAuth
    com_oauth = []
    for c in nossos:
        nome = c["nome_canal"]
        ch_id = yt_name_to_id.get(nome)
        if ch_id and ch_id in oauth_ids:
            com_oauth.append(c)

    # Depois busca inscritos mais recentes de cada um e filtra < MAX
    candidatos = []
    for c in com_oauth:
        hist = db.supabase.table("dados_canais_historico").select(
            "inscritos, data_coleta"
        ).eq("canal_id", c["id"]).order("data_coleta", desc=True).limit(1).execute()
        if not hist.data:
            continue  # sem dados de inscritos, não entra na leva
        inscritos = hist.data[0].get("inscritos")
        if inscritos is None or inscritos >= LEVA3_INSCRITOS_MAX:
            continue

        lingua_raw = c.get("lingua", "")
        lingua_full = LINGUA_MAP.get(lingua_raw, lingua_raw)
        candidatos.append({
            "channel_name": c["nome_canal"],
            "subnicho": c.get("subnicho", ""),
            "lingua": lingua_full,
            "inscritos": inscritos,
        })

    return sorted(candidatos, key=lambda x: (x["subnicho"], x["channel_name"]))


def _get_leva3_canais(force_refresh: bool = False) -> list[dict]:
    """Retorna canais da Leva 3, com cache de LEVA3_CACHE_TTL segundos."""
    now = time.time()
    if (not force_refresh
        and _leva3_cache["canais"]
        and (now - _leva3_cache["at"]) < LEVA3_CACHE_TTL):
        return _leva3_cache["canais"]
    try:
        canais = _compute_leva3_canais()
        _leva3_cache["canais"] = canais
        _leva3_cache["at"] = now
        return canais
    except Exception as e:
        logger.error(f"[leva3] Erro computando: {e}")
        # Se falhou, devolve ultimo cache (mesmo expirado) pra nao derrubar endpoint
        return _leva3_cache["canais"] or []


def _get_leva3_canal_names(force_refresh: bool = False) -> list[str]:
    """Apenas os nomes dos canais da Leva 3 (pra filtro IN)."""
    return [c["channel_name"] for c in _get_leva3_canais(force_refresh)]

_batch_gerar_status: dict = {}  # batch_id -> {status, total, completed, current, results, errors}


class BatchGerarRequest(BaseModel):
    mode: str  # "subnicho", "leva", "todos"
    subnicho: Optional[str] = None  # Se mode=subnicho
    leva: Optional[int] = None  # Se mode=leva (1 ou 2)


def _get_oauth_channels_by_subnichos(subnichos: list[str]) -> list[dict]:
    """Retorna canais com OAuth agrupados pelos subnichos especificados."""
    oauth = db.supabase.table("yt_oauth_tokens").select("channel_id").execute()
    oauth_ids = {r["channel_id"] for r in (oauth.data or [])}

    yt = db.supabase.table("yt_channels").select(
        "channel_id, channel_name, subnicho, lingua"
    ).eq("is_active", True).execute()

    canais = []
    for ch in (yt.data or []):
        if (ch["channel_id"] in oauth_ids
            and ch.get("subnicho") in subnichos):
            lingua_raw = ch.get("lingua", "")
            lingua_full = LINGUA_MAP.get(lingua_raw, lingua_raw)  # pt -> Português
            canais.append({
                "channel_name": ch["channel_name"],
                "subnicho": ch["subnicho"],
                "lingua": lingua_full,
            })

    return sorted(canais, key=lambda c: (c["subnicho"], c["lingua"]))


@router.post("/batch-gerar")
async def batch_gerar(req: BatchGerarRequest, background_tasks: BackgroundTasks):
    """Gera scripts em batch: por subnicho, por leva (1/2/3), ou todos."""
    # Leva 3 tem lógica diferente: lista dinamica de canais, nao filtra por subnicho
    if req.mode == "leva" and req.leva == 3:
        canais = [
            {"channel_name": c["channel_name"], "subnicho": c["subnicho"], "lingua": c["lingua"]}
            for c in _get_leva3_canais()
        ]
        subnichos = sorted({c["subnicho"] for c in canais if c.get("subnicho")})
        if not canais:
            return {"status": "nenhum", "message": "Nenhum canal na Leva 3 (OAuth + <1000 inscritos)"}
    else:
        # Determinar subnichos (fluxo original Leva 1/2/subnicho/todos)
        if req.mode == "subnicho":
            if not req.subnicho:
                raise HTTPException(400, "subnicho obrigatorio quando mode=subnicho")
            subnichos = [req.subnicho]
        elif req.mode == "leva":
            if req.leva == 1:
                subnichos = LEVA_1_SUBNICHOS
            elif req.leva == 2:
                subnichos = LEVA_2_SUBNICHOS
            else:
                raise HTTPException(400, "leva deve ser 1, 2 ou 3")
        elif req.mode == "todos":
            subnichos = LEVA_1_SUBNICHOS + LEVA_2_SUBNICHOS
        else:
            raise HTTPException(400, "mode deve ser 'subnicho', 'leva' ou 'todos'")

        # Buscar canais OAuth dos subnichos
        canais = _get_oauth_channels_by_subnichos(subnichos)
        if not canais:
            return {"status": "nenhum", "message": "Nenhum canal com OAuth nos subnichos selecionados"}

    import uuid
    batch_id = str(uuid.uuid4())[:8]

    _batch_gerar_status[batch_id] = {
        "status": "running",
        "total": len(canais),
        "completed": 0,
        "current": None,
        "results": [],
        "errors": [],
    }

    background_tasks.add_task(_run_batch_gerar_bg, batch_id, canais)

    return {
        "batch_id": batch_id,
        "status": "running",
        "total": len(canais),
        "mode": req.mode,
        "subnichos": subnichos,
        "canais": [{"canal": c["channel_name"], "subnicho": c["subnicho"], "lingua": c["lingua"]} for c in canais],
    }


@router.get("/batch-gerar-status/{batch_id}")
async def batch_gerar_status(batch_id: str):
    """Status do batch de geração."""
    status = _batch_gerar_status.get(batch_id)
    if not status:
        raise HTTPException(404, "Batch nao encontrado")
    return status


def _run_batch_gerar_bg(batch_id: str, canais: list[dict]):
    """Gera scripts pra todos os canais em sequência."""
    status = _batch_gerar_status[batch_id]

    for i, canal_info in enumerate(canais):
        channel_name = canal_info["channel_name"]
        subnicho = canal_info["subnicho"]
        lingua = canal_info["lingua"]

        status["current"] = {
            "index": i + 1,
            "canal": channel_name,
            "subnicho": subnicho,
            "lingua": lingua,
            "step": "analisando",
        }

        try:
            # 1. Analista
            status["current"]["step"] = "analisando"
            from _features.shorts_production.analyst import analyze_channel
            analysis = analyze_channel(channel_name, subnicho)

            # 2. Sugerir tema
            status["current"]["step"] = "sugerindo tema"
            from _features.shorts_production.theme_suggester import suggest_themes
            temas = suggest_themes(
                canal=channel_name,
                subnicho=subnicho,
                lingua=lingua,
                temas_bloqueados=analysis.get("temas_bloqueados", ""),
                video_ref_titulo=analysis.get("video_ref_titulo", ""),
            )

            if not temas:
                status["errors"].append({"canal": channel_name, "error": "sem temas sugeridos"})
                continue

            # Auto-selecionar 1o tema
            tema = temas[0]
            topic = tema.get("titulo", tema) if isinstance(tema, dict) else tema

            # 3. Pipeline (scriptwriter + diretor)
            status["current"]["step"] = "gerando script"
            from _features.shorts_production.pipeline import run_production
            result = run_production(
                topic=topic,
                canal=channel_name,
                canal_id=0,
                subnicho=subnicho,
                lingua=lingua,
                tom=analysis.get("tom", ""),
                formato=analysis.get("formato", "livre"),
                video_ref=analysis.get("video_ref", ""),
                video_ref_titulo=analysis.get("video_ref_titulo", ""),
            )

            # 4. Escrever na planilha
            status["current"]["step"] = "salvando"
            sheets_row_num = None
            try:
                from _features.shorts_production.sheets_writer import write_production_to_sheet
                pj = result.get("producao_json", {})
                cenas = pj.get("cenas", [])
                prompts_img = "\n".join(c.get("prompt_imagem", "") for c in cenas)
                prompts_anim = "\n".join(c.get("prompt_animacao", "") for c in cenas)

                sheets_row_num = write_production_to_sheet(channel_name, subnicho, {
                    "data": datetime.utcnow().strftime("%d/%m/%Y"),
                    "tom": analysis.get("tom", ""),
                    "titulo": result.get("titulo", ""),
                    "descricao": pj.get("descricao", ""),
                    "script": pj.get("script", ""),
                    "prompts_imagem": prompts_img,
                    "prompts_animacao": prompts_anim,
                    "formato": analysis.get("formato", "livre"),
                    "video_ref": analysis.get("video_ref", ""),
                })
            except Exception as sheet_err:
                logger.warning(f"[batch-gerar] Planilha erro: {str(sheet_err)[:100]}")

            # 5. Salvar no Supabase
            insert_data = {
                "canal": result["canal"],
                "subnicho": result["subnicho"],
                "lingua": lingua,
                "titulo": result["titulo"],
                "tom": analysis.get("tom", ""),
                "formato": analysis.get("formato", "livre"),
                "video_ref": analysis.get("video_ref", ""),
                "sheets_row_num": sheets_row_num,
                "producao_json": result["producao_json"],
                "drive_link": result["drive_link"],
                "status": "producao",
            }
            db.supabase.table("shorts_production").insert(insert_data).execute()

            status["completed"] += 1
            status["results"].append({
                "canal": channel_name,
                "titulo": result["titulo"],
                "tom": analysis.get("tom", ""),
                "formato": analysis.get("formato", "livre"),
            })

            try:
                logger.info(f"[batch-gerar] {i+1}/{len(canais)}: {channel_name} -> {result['titulo']}")
            except UnicodeEncodeError:
                logger.info(f"[batch-gerar] {i+1}/{len(canais)}: done")

        except Exception as e:
            # Retry 1x antes de desistir
            logger.warning(f"[batch-gerar] ERRO {channel_name} (tentativa 1): {str(e)[:150]}. Retentando...")
            import time as _time
            _time.sleep(5)
            try:
                status["current"]["step"] = "retry"
                from _features.shorts_production.analyst import analyze_channel as _ac
                analysis2 = _ac(channel_name, subnicho)
                from _features.shorts_production.theme_suggester import suggest_themes as _st
                temas2 = _st(canal=channel_name, subnicho=subnicho, lingua=lingua,
                             temas_bloqueados=analysis2.get("temas_bloqueados", ""),
                             video_ref_titulo=analysis2.get("video_ref_titulo", ""))
                if temas2:
                    tema2 = temas2[0]
                    topic2 = tema2.get("titulo", tema2) if isinstance(tema2, dict) else tema2
                    from _features.shorts_production.pipeline import run_production as _rp
                    result2 = _rp(topic=topic2, canal=channel_name, canal_id=0, subnicho=subnicho,
                                  lingua=lingua, tom=analysis2.get("tom", ""),
                                  formato=analysis2.get("formato", "livre"),
                                  video_ref=analysis2.get("video_ref", ""),
                                  video_ref_titulo=analysis2.get("video_ref_titulo", ""))
                    # Salvar
                    sheets_row_num2 = None
                    try:
                        from _features.shorts_production.sheets_writer import write_production_to_sheet as _ws
                        pj2 = result2.get("producao_json", {})
                        cenas2 = pj2.get("cenas", [])
                        sheets_row_num2 = _ws(channel_name, subnicho, {
                            "data": datetime.utcnow().strftime("%d/%m/%Y"),
                            "tom": analysis2.get("tom", ""), "titulo": result2.get("titulo", ""),
                            "descricao": pj2.get("descricao", ""), "script": pj2.get("script", ""),
                            "prompts_imagem": "\n".join(c.get("prompt_imagem", "") for c in cenas2),
                            "prompts_animacao": "\n".join(c.get("prompt_animacao", "") for c in cenas2),
                            "formato": analysis2.get("formato", "livre"),
                            "video_ref": analysis2.get("video_ref", ""),
                        })
                    except Exception:
                        pass
                    db.supabase.table("shorts_production").insert({
                        "canal": result2["canal"], "subnicho": result2["subnicho"], "lingua": lingua,
                        "titulo": result2["titulo"], "tom": analysis2.get("tom", ""),
                        "formato": analysis2.get("formato", "livre"),
                        "video_ref": analysis2.get("video_ref", ""), "sheets_row_num": sheets_row_num2,
                        "producao_json": result2["producao_json"], "drive_link": result2["drive_link"],
                        "status": "producao",
                    }).execute()
                    status["completed"] += 1
                    status["results"].append({"canal": channel_name, "titulo": result2["titulo"],
                                              "tom": analysis2.get("tom", ""), "formato": analysis2.get("formato", "livre")})
                    logger.info(f"[batch-gerar] {channel_name}: RETRY OK -> {result2['titulo']}")
                else:
                    status["errors"].append({"canal": channel_name, "error": f"retry falhou: sem temas"})
            except Exception as e2:
                status["errors"].append({"canal": channel_name, "error": f"retry falhou: {str(e2)[:150]}"})
                logger.error(f"[batch-gerar] ERRO {channel_name} (retry): {str(e2)[:150]}")

    status["status"] = "done"
    status["current"] = None
    logger.info(f"[batch-gerar] Concluido: {status['completed']}/{len(canais)}, {len(status['errors'])} erros")


# === Batch Upload ===

_batch_upload_status: dict = {}  # batch_id -> {status, total, completed, current, errors}


class BatchUploadRequest(BaseModel):
    delay_seconds: int = 25
    production_ids: Optional[list[int]] = None  # Se None, pega todos prontos com OAuth


@router.post("/batch-upload")
async def batch_upload(req: BatchUploadRequest, background_tasks: BackgroundTasks):
    """Upload em fila: 1 por 1 com delay entre cada."""
    if req.production_ids:
        # IDs específicos passados pelo frontend
        prontos = db.supabase.table("shorts_production").select(
            "id, canal, titulo, drive_link"
        ).in_("id", req.production_ids).eq("status", "pronto").is_("youtube_video_id", "null").execute()
    else:
        # Fallback: todos prontos sem upload
        prontos = db.supabase.table("shorts_production").select(
            "id, canal, titulo, drive_link"
        ).eq("status", "pronto").is_("youtube_video_id", "null").execute()

    if not prontos.data:
        return {"status": "nenhum", "message": "Nenhum short pronto pra upload"}

    import uuid
    batch_id = str(uuid.uuid4())[:8]
    ids = [p["id"] for p in prontos.data]

    _batch_upload_status[batch_id] = {
        "status": "running",
        "total": len(ids),
        "completed": 0,
        "current": None,
        "errors": [],
    }

    background_tasks.add_task(
        _run_batch_upload_bg, batch_id, ids, req.delay_seconds
    )

    return {
        "batch_id": batch_id,
        "status": "running",
        "total": len(ids),
        "delay_seconds": req.delay_seconds,
        "shorts": [{"id": p["id"], "canal": p["canal"], "titulo": p["titulo"]} for p in prontos.data],
    }


@router.get("/batch-upload-status/{batch_id}")
async def batch_upload_status(batch_id: str):
    """Status do batch upload."""
    status = _batch_upload_status.get(batch_id)
    if not status:
        raise HTTPException(404, "Batch nao encontrado")
    return status


def _run_batch_upload_bg(batch_id: str, production_ids: list[int], delay_seconds: int):
    """Upload 1 por 1 com delay entre cada."""
    import time

    status = _batch_upload_status[batch_id]
    total = len(production_ids)

    for i, prod_id in enumerate(production_ids):
        try:
            result = db.supabase.table("shorts_production").select("*").eq("id", prod_id).single().execute()
            if not result.data:
                status["errors"].append({"id": prod_id, "error": "nao encontrado"})
                continue

            if result.data.get("youtube_video_id"):
                status["completed"] += 1
                continue

            drive_link = result.data.get("drive_link", "")
            video_path = os.path.join(drive_link, "video_final.mp4") if drive_link else ""
            if not video_path or not os.path.exists(video_path):
                status["errors"].append({"id": prod_id, "error": f"video nao encontrado: {drive_link}"})
                continue

            status["current"] = {
                "id": prod_id,
                "canal": result.data.get("canal", ""),
                "titulo": result.data.get("titulo", ""),
                "index": i + 1,
            }

            logger.info(f"[batch-upload] {i+1}/{total}: {result.data.get('canal')} - uploading...")
            _run_youtube_upload_bg(prod_id, result.data, video_path)
            status["completed"] += 1

            # Delay entre uploads (exceto no ultimo)
            if i < total - 1:
                logger.info(f"[batch-upload] Aguardando {delay_seconds}s...")
                time.sleep(delay_seconds)

        except Exception as e:
            status["errors"].append({"id": prod_id, "error": str(e)[:100]})

    status["status"] = "done"
    status["current"] = None
    logger.info(f"[batch-upload] Concluido: {status['completed']}/{total} uploads, {len(status['errors'])} erros")


@router.get("/leva3-channels")
async def leva3_channels(refresh: bool = False):
    """Lista dinamica da Leva 3: canais com OAuth configurado E <1000 inscritos.

    Cache de 5min (passa ?refresh=true pra forçar recomputo).
    Retorna: {count, threshold, canais: [{channel_name, subnicho, lingua, inscritos}]}
    """
    canais = _get_leva3_canais(force_refresh=refresh)
    return {
        "count": len(canais),
        "threshold": LEVA3_INSCRITOS_MAX,
        "canais": canais,
        "cached_at": _leva3_cache.get("at", 0),
    }


@router.get("/canais-com-oauth")
async def canais_com_oauth():
    """Lista canais nossos que tem OAuth — cruzando canais_monitorados com yt_channels."""
    # Canais nossos ativos (shorts factory)
    nossos = db.supabase.table("canais_monitorados").select(
        "id, nome_canal, subnicho, lingua"
    ).eq("tipo", "nosso").eq("status", "ativo").execute()

    # Canais no yt_channels (upload system)
    yt = db.supabase.table("yt_channels").select(
        "channel_id, channel_name"
    ).eq("is_active", True).execute()
    yt_nomes = {c["channel_name"] for c in yt.data}

    # OAuth tokens
    oauth = db.supabase.table("yt_oauth_tokens").select("channel_id").execute()
    oauth_ids = {r["channel_id"] for r in oauth.data}

    # Canal com OAuth = existe no yt_channels E tem token
    yt_name_to_id = {c["channel_name"]: c["channel_id"] for c in yt.data}

    com_oauth = []
    sem_oauth = []
    for c in nossos.data:
        nome = c["nome_canal"]
        item = {
            "nome_canal": nome,
            "subnicho": c.get("subnicho", ""),
            "lingua": c.get("lingua", ""),
        }
        ch_id = yt_name_to_id.get(nome)
        if ch_id and ch_id in oauth_ids:
            item["channel_id"] = ch_id
            com_oauth.append(item)
        else:
            sem_oauth.append(item)

    return {"com_oauth": com_oauth, "sem_oauth": sem_oauth}


@router.post("/collect-subs")
async def collect_shorts_subs(background_tasks: BackgroundTasks):
    """Coleta subscribers gained/lost dos shorts publicados via YouTube Analytics API."""
    background_tasks.add_task(_run_subs_collection_bg)
    return {"status": "collecting", "message": "Coleta de subscribers iniciada"}


def _run_subs_collection_bg():
    """Coleta subscribers gained por short via YouTube Analytics API."""
    try:
        from dotenv import load_dotenv
        load_dotenv()
        from _features.yt_uploader.oauth_manager import OAuthManager
        from googleapiclient.discovery import build
        from datetime import date

        # Buscar todos shorts publicados com youtube_video_id
        shorts = db.supabase.table("shorts_production").select(
            "youtube_video_id, canal"
        ).neq("youtube_video_id", "null").execute()

        if not shorts.data:
            logger.info("[subs] Nenhum short publicado pra coletar")
            return

        # Agrupar video_ids por canal
        canais = {}
        for s in shorts.data:
            vid = s.get("youtube_video_id")
            canal = s.get("canal")
            if vid and canal:
                if canal not in canais:
                    canais[canal] = []
                canais[canal].append(vid)

        # Buscar channel_id pra cada canal
        yt_channels = db.supabase.table("yt_channels").select(
            "channel_id, channel_name"
        ).eq("is_active", True).execute()

        # Match por nome (com fallback normalizado)
        import unicodedata
        name_to_id = {}
        for ch in yt_channels.data:
            name_to_id[ch["channel_name"]] = ch["channel_id"]
            norm = unicodedata.normalize("NFD", ch["channel_name"]).encode("ascii", "ignore").decode().lower()
            name_to_id[norm] = ch["channel_id"]

        today = date.today().isoformat()
        total_collected = 0

        for canal, video_ids in canais.items():
            # Encontrar channel_id
            channel_id = name_to_id.get(canal)
            if not channel_id:
                canal_norm = unicodedata.normalize("NFD", canal).encode("ascii", "ignore").decode().lower()
                channel_id = name_to_id.get(canal_norm)
            if not channel_id:
                logger.warning(f"[subs] Canal '{canal}' sem channel_id, pulando")
                continue

            try:
                creds = OAuthManager.get_valid_credentials(channel_id)
                import requests as req

                resp = req.get(
                    "https://youtubeanalytics.googleapis.com/v2/reports",
                    params={
                        "ids": "channel==MINE",
                        "startDate": "2026-01-01",
                        "endDate": today,
                        "metrics": "subscribersGained,subscribersLost",
                        "dimensions": "video",
                        "sort": "-subscribersGained",
                        "maxResults": "200",
                    },
                    headers={"Authorization": f"Bearer {creds.token}"},
                    timeout=30,
                )

                if resp.status_code != 200:
                    logger.warning(f"[subs] Analytics API erro {resp.status_code} pra {canal}: {resp.text[:100]}")
                    continue

                result = resp.json()
                video_ids_set = set(video_ids)
                for row in result.get("rows", []):
                    vid = row[0]
                    if vid in video_ids_set:
                        subs_gained = row[1]
                        subs_lost = row[2]

                        try:
                            db.supabase_service.table("shorts_subs").insert({
                                "video_id": vid,
                                "date": today,
                                "subs_gained": subs_gained,
                                "subs_lost": subs_lost,
                            }).execute()
                        except Exception:
                            db.supabase_service.table("shorts_subs").update({
                                "subs_gained": subs_gained,
                                "subs_lost": subs_lost,
                            }).eq("video_id", vid).eq("date", today).execute()

                        total_collected += 1

            except Exception as e:
                logger.warning(f"[subs] Erro no canal {canal}: {e}")
                continue

        logger.info(f"[subs] Coleta concluida: {total_collected} shorts atualizados")

    except Exception as e:
        logger.error(f"[subs] Erro geral: {e}")


@router.get("/analytics")
async def shorts_analytics():
    """Retorna analytics de todos os shorts publicados (batch query, rapido)."""
    # 1. Buscar todos shorts publicados
    shorts = db.supabase.table("shorts_production").select(
        "id, canal, subnicho, lingua, titulo, youtube_video_id, status, created_at"
    ).neq("youtube_video_id", "null").order("created_at", desc=True).execute()

    if not shorts.data:
        return {"totals": {}, "by_subnicho": {}, "shorts": []}

    video_ids = [s["youtube_video_id"] for s in shorts.data if s.get("youtube_video_id")]

    # 2. Batch: buscar TODAS metricas de uma vez
    metrics = {}
    if video_ids:
        all_hist = db.supabase.table("videos_historico").select(
            "video_id, views_atuais, likes, comentarios, data_coleta"
        ).in_("video_id", video_ids).order("data_coleta", desc=True).execute()
        # Pegar ultima coleta por video
        for h in all_hist.data:
            vid = h["video_id"]
            if vid not in metrics:
                metrics[vid] = h

    # 3. Batch: buscar TODOS subs de uma vez
    subs = {}
    if video_ids:
        all_subs = db.supabase.table("shorts_subs").select(
            "video_id, subs_gained, subs_lost"
        ).in_("video_id", video_ids).execute()
        for r in all_subs.data:
            vid = r["video_id"]
            if vid not in subs:
                subs[vid] = {"gained": 0, "lost": 0}
            subs[vid]["gained"] += r["subs_gained"]
            subs[vid]["lost"] += r["subs_lost"]

    # 4. Montar resposta agrupada por subnicho > canal > shorts
    shorts_list = []
    by_subnicho = {}
    totals = {"total_shorts": 0, "total_views": 0, "total_likes": 0, "total_comments": 0, "total_subs_gained": 0}

    for s in shorts.data:
        vid = s.get("youtube_video_id")
        m = metrics.get(vid, {})
        sub = subs.get(vid, {})

        views = m.get("views_atuais", 0) or 0
        likes = m.get("likes", 0) or 0
        comments = m.get("comentarios", 0) or 0
        subs_gained = sub.get("gained", 0)

        short_data = {
            "id": s["id"],
            "titulo": s["titulo"],
            "canal": s["canal"],
            "subnicho": s["subnicho"],
            "lingua": s["lingua"],
            "youtube_video_id": vid,
            "views": views,
            "likes": likes,
            "comments": comments,
            "subs_gained": subs_gained,
            "created_at": s["created_at"],
        }
        shorts_list.append(short_data)

        totals["total_shorts"] += 1
        totals["total_views"] += views
        totals["total_likes"] += likes
        totals["total_comments"] += comments
        totals["total_subs_gained"] += subs_gained

        # Agrupar por subnicho > canal
        subnicho = s["subnicho"]
        canal = s["canal"]
        if subnicho not in by_subnicho:
            by_subnicho[subnicho] = {}
        if canal not in by_subnicho[subnicho]:
            by_subnicho[subnicho][canal] = {"canal": canal, "subnicho": subnicho, "lingua": s["lingua"], "shorts_count": 0, "views": 0, "likes": 0, "comments": 0, "subs_gained": 0, "shorts": []}
        ch = by_subnicho[subnicho][canal]
        ch["shorts_count"] += 1
        ch["views"] += views
        ch["likes"] += likes
        ch["comments"] += comments
        ch["subs_gained"] += subs_gained
        ch["shorts"].append(short_data)

    return {
        "totals": totals,
        "by_subnicho": {k: list(v.values()) for k, v in by_subnicho.items()},
        "shorts": shorts_list,
    }


@router.get("/subnichos")
async def listar_subnichos():
    """Lista subnichos dos nossos canais."""
    result = db.supabase.table("canais_monitorados").select("subnicho").eq("tipo", "nosso").eq("status", "ativo").execute()
    EXCLUDED_SUBNICHOS = {"Lições de Vida", "Licoes de Vida", "Registros Malditos"}
    SUBNICHO_ORDER = [
        "Monetizados", "Reis Perversos", "Historias Sombrias", "Culturas Macabras",
        "Relatos de Guerra", "Frentes de Guerra", "Guerras e Civilizações",
        "Guerras e Civilizacoes", "Desmonetizados",
    ]
    all_subnichos = set(
        item["subnicho"] for item in result.data
        if item.get("subnicho") and item["subnicho"] not in EXCLUDED_SUBNICHOS
    )
    # Ordenar pela ordem do dashboard principal
    ordered = [s for s in SUBNICHO_ORDER if s in all_subnichos]
    remaining = sorted(all_subnichos - set(ordered))
    return {"subnichos": ordered + remaining}


@router.get("/canais")
async def listar_canais(subnicho: str):
    """Lista canais de um subnicho, marcando quem tem OAuth."""
    result = db.supabase.table("canais_monitorados").select("id,nome_canal,subnicho,lingua").eq("tipo", "nosso").eq("status", "ativo").eq("subnicho", subnicho).execute()

    # Checar quais tem OAuth (comparar com yt_channels)
    yt = db.supabase.table("yt_channels").select("channel_name").eq("is_active", True).execute()
    yt_nomes = {c["channel_name"] for c in yt.data}

    canais = []
    for c in result.data:
        c["has_oauth"] = c["nome_canal"] in yt_nomes
        canais.append(c)

    # OAuth primeiro, sem OAuth por ultimo
    canais.sort(key=lambda c: (0 if c["has_oauth"] else 1, c["nome_canal"]))

    return {"canais": canais}
