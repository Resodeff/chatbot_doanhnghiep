import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

def _int(name, default):
    return int(os.getenv(name, default))

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen3-sale:latest")

TEMPERATURE = float(os.getenv("TEMPERATURE", "0.5"))
NUM_CTX = _int("NUM_CTX", 4096)
MAX_TOKENS = _int("MAX_TOKENS", 400)
KEEP_ALIVE = os.getenv("KEEP_ALIVE", "30m")
TIMEOUT_SECONDS = _int("TIMEOUT_SECONDS", 120)

MAX_HISTORY_TURNS = _int("MAX_HISTORY_TURNS", 6)
MAX_PRODUCTS = _int("MAX_PRODUCTS", 8)

SYSTEM_PROMPT_FILE = BASE_DIR / os.getenv("SYSTEM_PROMPT_FILE", "system_prompt.txt")

def load_system_prompt() -> str:
    """Đọc mỗi lần gọi để sửa file là có hiệu lực ngay, không cần restart."""
    return SYSTEM_PROMPT_FILE.read_text(encoding="utf-8").strip()
