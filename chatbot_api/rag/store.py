"""Khởi tạo và trả về Chroma collection dùng chung toàn app."""
import chromadb
import config

_client = None
_collection = None

COLLECTION_NAME = "linhkien"


def get_collection():
    """
    Trả về collection (tạo nếu chưa có).
    Dùng embedding_function=None vì chúng ta tự tính vector bằng Ollama.
    """
    global _client, _collection
    if _collection is not None:
        return _collection

    # Workaround cho Chroma + sqlite3 cũ trên Windows / một số môi trường
    try:
        import pysqlite3  # noqa: F401
        import sys
        sys.modules["sqlite3"] = sys.modules.pop("pysqlite3")
    except ImportError:
        pass

    _client = chromadb.PersistentClient(path=str(config.CHROMA_DIR))
    _collection = _client.get_or_create_collection(
        name=COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"},
    )
    return _collection


def reset_collection():
    """Xóa collection cũ và tạo lại (dùng khi /reindex)."""
    global _client, _collection
    get_collection()   # đảm bảo _client đã khởi tạo
    _client.delete_collection(COLLECTION_NAME)
    _collection = _client.create_collection(
        name=COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"},
    )
    return _collection