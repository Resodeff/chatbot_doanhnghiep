import logging
import config
import ollama_client
from fastapi import FastAPI, HTTPException, BackgroundTasks
from pydantic import BaseModel, Field
from prompting import build_messages, clean_reply
from rag.retriever import retrieve
from rag.indexer import reindex as _reindex
from rag.store import get_collection

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Chatbot tư vấn linh kiện")


class Turn(BaseModel):
    role: str
    content: str


class Product(BaseModel):
    ten: str
    gia: float
    thong_so: str = ""


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=1000)
    history: list[Turn] = []
    products: list[Product] = []   # tuỳ chọn — nếu rỗng thì tự gọi RAG


class ChatResponse(BaseModel):
    reply: str
    model: str


class ReindexResponse(BaseModel):
    ok: bool
    indexed: int
    message: str


# ── Health ────────────────────────────────────────────────────────────────────

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
        "ok": loaded,
        "ollama": "ok",
        "model": config.OLLAMA_MODEL,
        "model_co_san": loaded,
        "models_hien_co": models,
        "chroma_documents": n_docs,
    }


# ── Reindex ───────────────────────────────────────────────────────────────────

@app.post("/reindex", response_model=ReindexResponse)
async def reindex():
    """Kéo toàn bộ sản phẩm từ Django, embed và nạp lại Chroma."""
    try:
        total = await _reindex()
    except Exception as e:
        logger.exception("Reindex thất bại")
        raise HTTPException(status_code=500, detail=str(e))
    return ReindexResponse(ok=True, indexed=total, message=f"Đã nạp {total} sản phẩm vào Chroma.")


# ── Chat ──────────────────────────────────────────────────────────────────────

@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    # Nếu client không gửi products → tự gọi RAG
    if req.products:
        products = [p.model_dump() for p in req.products]
    else:
        try:
            products = await retrieve(
                message=req.message,
                history=[t.model_dump() for t in req.history],
            )
        except Exception as e:
            logger.warning("RAG retrieve lỗi, tiếp tục với danh sách rỗng: %s", e)
            products = []

    messages = build_messages(
        system_prompt=config.load_system_prompt(),
        message=req.message,
        history=[t.model_dump() for t in req.history],
        products=products,
        max_turns=config.MAX_HISTORY_TURNS,
        max_products=config.MAX_PRODUCTS,
    )
    try:
        raw = await ollama_client.chat(messages)
        logger.debug("RAW reply: %s", repr(raw[:200]))
    except ollama_client.OllamaError as e:
        raise HTTPException(status_code=503, detail=str(e))

    reply = clean_reply(raw)
    if not reply:
        raise HTTPException(status_code=502, detail="Model trả về rỗng")
    return ChatResponse(reply=reply, model=config.OLLAMA_MODEL)