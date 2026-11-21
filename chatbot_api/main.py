from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

import config
import logging
import ollama_client
from prompting import build_messages, clean_reply

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
    products: list[Product] = []     # Django tìm sẵn trong DB rồi gửi sang


class ChatResponse(BaseModel):
    reply: str
    model: str

@app.get("/health")
async def health():
    try:
        models = await ollama_client.list_models()
        logging.exception("DEBUG models:", models)
    except Exception:
        return {"ok": False, "ollama": "không kết nối được", "model": config.OLLAMA_MODEL}
    loaded = config.OLLAMA_MODEL in models or f"{config.OLLAMA_MODEL}:latest" in models
    return {"ok": loaded, "ollama": "ok", "model": config.OLLAMA_MODEL,
            "model_co_san": loaded, "models_hien_co": models}

@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    messages = build_messages(
        system_prompt=config.load_system_prompt(),
        message=req.message,
        history=[t.model_dump() for t in req.history],
        products=[p.model_dump() for p in req.products],
        max_turns=config.MAX_HISTORY_TURNS,
        max_products=config.MAX_PRODUCTS,
    )
    try:
        raw = await ollama_client.chat(messages)
        print("DEBUG raw:", repr(raw[:200]))
    except ollama_client.OllamaError as e:
        raise HTTPException(status_code=503, detail=str(e))
    reply = clean_reply(raw)
    if not reply:
        raise HTTPException(status_code=502, detail="Model trả về rỗng")
    return ChatResponse(reply=reply, model=config.OLLAMA_MODEL)


