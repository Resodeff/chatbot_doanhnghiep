import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

def _int(name, default):
    return int(os.getenv(name, default))

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen3-sale:latest")

TEMPERATURE = float(os.getenv("TEMPERATURE", "0.4"))
NUM_CTX = _int("NUM_CTX", 4096)
MAX_TOKENS = _int("MAX_TOKENS", 2400)
KEEP_ALIVE = os.getenv("KEEP_ALIVE", "30m")
TIMEOUT_SECONDS = _int("TIMEOUT_SECONDS", 120)

MAX_HISTORY_TURNS = _int("MAX_HISTORY_TURNS", 6)
MAX_PRODUCTS      = _int("MAX_PRODUCTS", 8)

# ── Chat history (SQLite) ─────────────────────────────────────────────────────
CHAT_DB_PATH      = BASE_DIR / os.getenv("CHAT_DB_PATH", "data/chat_history.sqlite3")
MAX_STORED_MSGS   = _int("MAX_STORED_MSGS", 40)   # tổng user+assistant rows lưu trong DB
HISTORY_FOR_LLM   = _int("HISTORY_FOR_LLM", 12)   # số turns gần nhất đưa vào prompt

SYSTEM_PROMPT_FILE = BASE_DIR / os.getenv("SYSTEM_PROMPT_FILE", "system_prompt.txt")

# ── RAG ──────────────────────────────────────────────────────────────────────
EMBED_MODEL         = os.getenv("EMBED_MODEL", "nomic-embed-text:latest")
CHROMA_DIR          = BASE_DIR / os.getenv("CHROMA_DIR", "chroma_db")
DJANGO_EXPORT_URL   = os.getenv("DJANGO_EXPORT_URL", "http://127.0.0.1:8000/api/linhkien/export/")
DJANGO_EXPORT_TOKEN = os.getenv("DJANGO_EXPORT_TOKEN", "")
RAG_TOP_K           = _int("RAG_TOP_K", 6)
RAG_FETCH_K         = _int("RAG_FETCH_K", 30)

def load_system_prompt() -> str:
    """Đọc mỗi lần gọi để sửa file là có hiệu lực ngay, không cần restart."""
    return SYSTEM_PROMPT_FILE.read_text(encoding="utf-8").strip()