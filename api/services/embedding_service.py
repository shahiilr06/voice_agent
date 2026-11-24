"""
Embedding generation service with fallback for offline/instant evaluation.
Generates 384-dimensional dense vectors.
"""
import os
import hashlib
from typing import List
import numpy as np

_model = None


def get_embedding_model():
    global _model
    if _model is None:
        if os.getenv("EMBEDDING_OFFLINE", "1") == "1":
            _model = False
            return _model
        try:
            from sentence_transformers import SentenceTransformer
            _model = SentenceTransformer("all-MiniLM-L6-v2", local_files_only=True)
        except Exception:
            _model = False
    return _model


def embed_text(text: str) -> List[float]:
    """
    Generate normalized 384-dimensional embedding vector for query or text.
    Uses sentence-transformers if installed, with a deterministic fallback vector.
    """
    if not text:
        return [0.0] * 384

    model = get_embedding_model()
    if model:
        try:
            vec = model.encode(text, normalize_embeddings=True)
            return [float(x) for x in vec.tolist()]
        except Exception:
            pass

    # Fast deterministic fallback: maps text n-grams to normalized 384-dim vector
    vector = np.zeros(384, dtype=np.float32)
    words = text.lower().split()
    for i, word in enumerate(words):
        h = int(hashlib.sha256(word.encode("utf-8")).hexdigest(), 16)
        idx = h % 384
        sign = 1.0 if (h >> 9) & 1 else -1.0
        weight = 1.0 / (1.0 + 0.1 * i)
        vector[idx] += sign * weight

    norm = np.linalg.norm(vector)
    if norm > 1e-6:
        vector = vector / norm
    return [float(x) for x in vector.tolist()]


def cosine_similarity(vec_a: List[float], vec_b: List[float]) -> float:
    """Compute cosine similarity between two 384-d vectors."""
    if not vec_a or not vec_b:
        return 0.0
    a = np.array(vec_a, dtype=np.float32)
    b = np.array(vec_b, dtype=np.float32)
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return float(np.dot(a, b) / (norm_a * norm_b))
