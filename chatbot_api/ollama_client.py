import httpx
import logging
import config

logger = logging.getLogger(__name__)

class OllamaError(Exception):
    pass

BUILD_PICK_SCHEMA = {
    "type": "object",
    "properties": {
        "CPU": {"type": "integer"},
        "MAIN": {"type": "integer"},
        "RAM": {"type": "integer"},
        "GPU": {"type": "integer"},
        "SSD": {"type": "integer"},
        "PSU": {"type": "integer"},
        "COOLER": {"type": "integer"},
        "CASE": {"type": "integer"},
    },
    "required": ["CPU", "MAIN", "RAM", "GPU", "SSD", "PSU", "COOLER", "CASE"],
}

BUILD_NOTES_SCHEMA = {
    "type": "object",
    "properties": {
        "mo_dau": {"type": "string"},
        "GPU": {"type": "string"},
        "CPU": {"type": "string"},
        "MAIN": {"type": "string"},
        "RAM": {"type": "string"},
        "SSD": {"type": "string"},
        "PSU": {"type": "string"},
        "COOLER": {"type": "string"},
        "CASE": {"type": "string"},
        "ket_thuc": {"type": "string"},
    },
    "required": ["mo_dau", "GPU", "CPU", "MAIN", "RAM", "SSD", "PSU", "COOLER", "CASE", "ket_thuc"],
}

async def chat(messages: list[dict], mode: str = "chat") -> str:
    payload = {
        "model": config.OLLAMA_MODEL,
        "messages": messages,
        "stream": False,
        "think": False,
        "keep_alive": config.KEEP_ALIVE,
        "options": {
            "temperature": 0.1 if mode == "pick" else (0.3 if mode == "notes" else config.TEMPERATURE),
            "num_ctx": max(config.NUM_CTX, 4096),
            "num_predict": 120 if mode == "pick" else config.MAX_TOKENS,
        },
    }

    if mode == "pick":
        payload["format"] = BUILD_PICK_SCHEMA
    elif mode == "notes":
        payload["format"] = BUILD_NOTES_SCHEMA

    logger.debug("PROMPT cuối:\n%s", messages[-1]["content"][:800])
    try:
        async with httpx.AsyncClient(timeout=config.TIMEOUT_SECONDS) as client:
            r = await client.post(f"{config.OLLAMA_URL}/api/chat", json=payload)
    except httpx.ConnectError:
        raise OllamaError("Không kết nối được Ollama. Ollama đã chạy chưa?")
    except httpx.TimeoutException:
        raise OllamaError("Ollama phản hồi quá lâu (timeout).")
    if r.status_code == 404:
        raise OllamaError(f"Ollama chưa có model '{config.OLLAMA_MODEL}'. Chạy: ollama list")
    if r.status_code != 200:
        raise OllamaError(f"Ollama lỗi {r.status_code}: {r.text[:200]}")
    data = r.json()
    content = data.get("message", {}).get("content", "").strip()
    logger.debug("REPLY: %s | done_reason=%s", repr(content[:200]), data.get("done_reason"))
    return content

async def list_models() -> list[str]:
    async with httpx.AsyncClient(timeout=5) as client:
        r = await client.get(f"{config.OLLAMA_URL}/api/tags")
    r.raise_for_status()
    return [m["name"] for m in r.json().get("models", [])]