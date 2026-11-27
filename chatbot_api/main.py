import logging
import config
import ollama_client
import chat_history
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, Field
from prompting import (
    build_messages,
    clean_reply,
    format_products_debug,
    is_multi_type_build,
    build_pick_messages,
    resolve_picked_products,
    build_present_build_messages,
    render_present_build,
)
from compatibility import check_compatibility
from rag.retriever import retrieve
from rag.indexer import reindex as _reindex
from rag.store import get_collection

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
_fh = logging.FileHandler("rag_debug.log", encoding="utf-8")
_fh.setLevel(logging.DEBUG)
_fh.setFormatter(logging.Formatter("%(asctime)s\n%(message)s\n" + "─" * 60))
logging.getLogger().addHandler(_fh)
logging.getLogger().setLevel(logging.DEBUG)
logger = logging.getLogger(__name__)

app = FastAPI(title="Chatbot tư vấn linh kiện")

@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={"status": "error", "message": str(exc.detail)},
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=422,
        content={"status": "error", "message": "Dữ liệu gửi lên không hợp lệ."},
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.exception("Lỗi chưa được xử lý: %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={"status": "error", "message": "Lỗi máy chủ, vui lòng thử lại sau."},
    )

class ChatRequest(BaseModel):
    message:    str  = Field(min_length=1, max_length=1000)
    session_id: str  = Field(default="default", max_length=128)


class ChatResponse(BaseModel):
    reply:      str
    model:      str
    session_id: str
    products:   list[dict] = []


class ClearRequest(BaseModel):
    session_id: str = "default"


class ReindexResponse(BaseModel):
    ok:      bool
    indexed: int
    products: int
    message: str


@app.get("/health")
async def health():
    try:
        models = await ollama_client.list_models()
    except Exception:
        return {"ok": False, "ollama": "không kết nối được", "model": config.OLLAMA_MODEL}
    loaded = config.OLLAMA_MODEL in models or f"{config.OLLAMA_MODEL}:latest" in models
    try:
        n_docs = get_collection().count()
    except Exception:
        n_docs = -1
    return {
        "ok":               loaded,
        "ollama":           "ok",
        "model":            config.OLLAMA_MODEL,
        "model_co_san":     loaded,
        "models_hien_co":   models,
        "chroma_documents": n_docs,
    }


@app.post("/reindex", response_model=ReindexResponse)
async def reindex():
    try:
        total_chunks, total_products = await _reindex()
    except Exception as e:
        logger.exception("Reindex thất bại")
        raise HTTPException(status_code=500, detail=str(e))
    return ReindexResponse(ok=True, indexed=total_chunks, products=total_products,
                       message=f"Đã nạp {total_products} sản phẩm ({total_chunks} chunks) vào Chroma.")


@app.post("/clear")
async def clear_history(req: ClearRequest):
    chat_history.clear(req.session_id)
    return {"ok": True, "session_id": req.session_id}

class CompatibilityRequest(BaseModel):
    product_ids: list[str] = Field(min_length=1)


class CompatibilityResponse(BaseModel):
    ok: bool
    compatible: bool
    warnings: list[str]
    products: list[dict] = []


@app.post("/compatibility", response_model=CompatibilityResponse)
async def compatibility(req: CompatibilityRequest):
    collection = get_collection()
    products: list[dict] = []
    for pid in req.product_ids:
        res = collection.get(where={"product_id": str(pid)}, limit=1)
        if res["metadatas"]:
            m = res["metadatas"][0]
            products.append({
                "product_id": str(pid),
                "loai": m.get("loai", ""),
                "ten": m.get("ten", ""),
                "thong_so": m.get("thong_so", ""),
            })
    warnings = check_compatibility(products)
    return CompatibilityResponse(ok=True, compatible=not warnings, warnings=warnings, products=products)


@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    session_id = req.session_id

    history = chat_history.get_history(session_id)
    logger.info("Session=%s | history=%d turns | msg='%s'",
                session_id, len(history) // 2, req.message[:80])

    try:
        products = await retrieve(
            message=req.message,
            history=history,
        )
    except Exception as e:
        logger.warning("RAG retrieve lỗi, tiếp tục với danh sách rỗng: %s", e)
        products = []

    logger.debug(
        "SESSION=%s | msg='%s'\n%s",
        session_id,
        req.message[:120],
        format_products_debug(products, limit=10),
    )

    sys_prompt = config.load_system_prompt()

    response_products: list[dict] = products

    try:
        if is_multi_type_build(products):
            pick_msgs = build_pick_messages(req.message, products)
            raw_pick = await ollama_client.chat(pick_msgs, mode="pick")
            selected_products = resolve_picked_products(raw_pick, products)
            response_products = selected_products
            present_msgs = build_present_build_messages(sys_prompt, req.message, selected_products)
            raw_notes = await ollama_client.chat(present_msgs, mode="notes")
            reply = render_present_build(raw_notes, selected_products)
            lines = [
                f"- [{p['loai']}] {p['ten']} — {int(p['gia']):,}".replace(",", ".") + "đ"
                for p in selected_products
            ]
            tong_tien = sum(int(p["gia"]) for p in selected_products)
            logger.debug(
            "BỘ MÁY ĐÃ CHỐT (AI đề xuất):\n%s\nTổng tiền: %sđ",
            "\n".join(lines),
            f"{tong_tien:,}".replace(",", "."),)
            compat_warnings = check_compatibility(selected_products)
            for w in compat_warnings:
                logger.warning("Cảnh báo tương thích: %s", w)
        else:
            messages = build_messages(
                system_prompt=sys_prompt,
                message=req.message,
                history=history,
                products=products,
                max_turns=config.MAX_HISTORY_TURNS,
                max_products=config.MAX_PRODUCTS,
            )
            raw = await ollama_client.chat(messages, mode="chat")
            reply = clean_reply(raw)
            logger.debug("REPLY (nhánh tự do):\n%s", reply)
    except ollama_client.OllamaError as e:
        raise HTTPException(status_code=503, detail=str(e))

    if not reply:
        raise HTTPException(status_code=502, detail="Model trả về rỗng")

    chat_history.append(req.message, reply, session_id)
    logger.info("Session=%s | reply saved | %d chars", session_id, len(reply))

    return ChatResponse(reply=reply, model=config.OLLAMA_MODEL, session_id=session_id, products=response_products)