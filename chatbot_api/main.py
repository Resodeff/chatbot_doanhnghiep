import logging
import config
import ollama_client
import chat_history
from fastapi import FastAPI, HTTPException
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
logging.getLogger("__main__").addHandler(_fh)
logging.getLogger("__main__").setLevel(logging.DEBUG)
logger = logging.getLogger(__name__)

app = FastAPI(title="Chatbot tư vấn linh kiện")


class ChatRequest(BaseModel):
    message:    str  = Field(min_length=1, max_length=1000)
    session_id: str  = Field(default="default", max_length=128)


class ChatResponse(BaseModel):
    reply:      str
    model:      str
    session_id: str


class ClearRequest(BaseModel):
    session_id: str = "default"


class ReindexResponse(BaseModel):
    ok:      bool
    indexed: int
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
        total = await _reindex()
    except Exception as e:
        logger.exception("Reindex thất bại")
        raise HTTPException(status_code=500, detail=str(e))
    return ReindexResponse(ok=True, indexed=total,
                           message=f"Đã nạp {total} sản phẩm vào Chroma.")


@app.post("/clear")
async def clear_history(req: ClearRequest):
    chat_history.clear(req.session_id)
    return {"ok": True, "session_id": req.session_id}


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

    try:
        if is_multi_type_build(products):
            pick_msgs = build_pick_messages(req.message, products)
            raw_pick = await ollama_client.chat(pick_msgs, mode="pick")
            selected_products = resolve_picked_products(raw_pick, products)
            present_msgs = build_present_build_messages(sys_prompt, req.message, selected_products)
            raw_notes = await ollama_client.chat(present_msgs, mode="notes")
            reply = render_present_build(raw_notes, selected_products)
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
    except ollama_client.OllamaError as e:
        raise HTTPException(status_code=503, detail=str(e))

    if not reply:
        raise HTTPException(status_code=502, detail="Model trả về rỗng")

    chat_history.append(req.message, reply, session_id)
    logger.info("Session=%s | reply saved | %d chars", session_id, len(reply))

    return ChatResponse(reply=reply, model=config.OLLAMA_MODEL, session_id=session_id)