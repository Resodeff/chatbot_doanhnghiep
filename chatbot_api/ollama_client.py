import httpx
import config

class OllamaError(Exception):
    pass

async def chat(messages: list[dict]) -> str:
    payload = {
        "model": config.OLLAMA_MODEL,
        "messages": messages,
        "stream": False,
        "think": False,
        "keep_alive": config.KEEP_ALIVE,
        "options": {
            "temperature": config.TEMPERATURE,
            "num_ctx": config.NUM_CTX,
            "num_predict": config.MAX_TOKENS,
        },
    }
    print("DEBUG prompt:", messages[-1]["content"][:800])
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
    print("DEBUG msg:", {k: (v[:150] if isinstance(v, str) else v) for k, v in data.get("message", {}).items()}, "| done_reason:", data.get("done_reason"))
    content = data.get("message", {}).get("content", "").strip()
    return content

async def list_models() -> list[str]:
    async with httpx.AsyncClient(timeout=5) as client:
        r = await client.get(f"{config.OLLAMA_URL}/api/tags")
    r.raise_for_status()
    return [m["name"] for m in r.json().get("models", [])]
