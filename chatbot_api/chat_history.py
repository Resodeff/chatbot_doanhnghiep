"""
Lưu và đọc lịch sử hội thoại theo session_id — SQLite, thread-safe.

Mỗi session là 1 chuỗi hội thoại độc lập (1 tab trình duyệt, 1 khách hàng...).
FastAPI tự gọi append() sau mỗi lượt và get_history() trước khi gọi LLM.
"""
import sqlite3
import time
import threading
from pathlib import Path
import config

_lock = threading.Lock()


def _connect() -> sqlite3.Connection:
    Path(config.CHAT_DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(config.CHAT_DB_PATH), check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def _ensure_schema(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT    NOT NULL DEFAULT 'default',
            role       TEXT    NOT NULL,
            content    TEXT    NOT NULL,
            ts         REAL    NOT NULL
        )
    """)
    # Index để query nhanh theo session
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_session
        ON messages (session_id, id)
    """)
    conn.commit()


def append(user_text: str, assistant_text: str,
           session_id: str = "default") -> None:
    """Ghi 1 lượt user + assistant, cắt bớt tin cũ nếu vượt cap."""
    now = time.time()
    with _lock:
        conn = _connect()
        try:
            _ensure_schema(conn)
            conn.execute(
                "INSERT INTO messages (session_id, role, content, ts) VALUES (?,?,?,?)",
                (session_id, "user", user_text, now),
            )
            conn.execute(
                "INSERT INTO messages (session_id, role, content, ts) VALUES (?,?,?,?)",
                (session_id, "assistant", assistant_text, now),
            )
            conn.commit()
            _trim(conn, session_id, config.MAX_STORED_MSGS)
        finally:
            conn.close()


def get_history(session_id: str = "default",
                limit: int | None = None) -> list[dict]:
    """
    Trả list [{'role': 'user'|'assistant', 'content': str}, ...]
    theo thứ tự thời gian (cũ → mới), tối đa `limit` turns gần nhất.
    """
    n = (limit or config.HISTORY_FOR_LLM) * 2   # mỗi turn = 2 rows
    with _lock:
        conn = _connect()
        try:
            _ensure_schema(conn)
            rows = conn.execute(
                """
                SELECT role, content FROM messages
                WHERE session_id = ?
                ORDER BY id DESC LIMIT ?
                """,
                (session_id, n),
            ).fetchall()
        finally:
            conn.close()
    return [{"role": r, "content": c} for r, c in reversed(rows)]


def clear(session_id: str = "default") -> None:
    """Xóa toàn bộ lịch sử của 1 session."""
    with _lock:
        conn = _connect()
        try:
            _ensure_schema(conn)
            conn.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
            conn.commit()
        finally:
            conn.close()


def _trim(conn: sqlite3.Connection, session_id: str, cap: int) -> None:
    row = conn.execute(
        "SELECT COUNT(*) FROM messages WHERE session_id = ?", (session_id,)
    ).fetchone()
    n = row[0] if row else 0
    if n <= cap:
        return
    to_drop = n - cap
    conn.execute(
        """
        DELETE FROM messages WHERE id IN (
            SELECT id FROM messages
            WHERE session_id = ?
            ORDER BY id ASC LIMIT ?
        )
        """,
        (session_id, to_drop),
    )
    conn.commit()