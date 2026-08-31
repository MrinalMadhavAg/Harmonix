"""Sentence embedding model wrapper.

The vector dimension is read from the loaded model at runtime and propagated
to the pgvector column -- it is never hardcoded. A model swap therefore
cannot silently produce vectors the database will reject.
"""
from __future__ import annotations

import logging
import threading

import numpy as np

from app.config import get_settings

log = logging.getLogger(__name__)

_model = None
_dim: int | None = None
_lock = threading.Lock()


def load_model():
    global _model, _dim
    if _model is not None:
        return _model
    with _lock:
        if _model is not None:
            return _model
        from sentence_transformers import SentenceTransformer

        name = get_settings().embedding_model
        log.info("Loading embedding model %s", name)
        model = SentenceTransformer(name)

        # sentence-transformers renamed this in 6.x. Read whichever the
        # installed version provides rather than assuming a pinned release --
        # the dimension flows into the pgvector column, so guessing is not an
        # option.
        getter = getattr(model, "get_embedding_dimension", None) or getattr(
            model, "get_sentence_embedding_dimension"
        )
        dim = int(getter())
        log.info("Embedding model ready (dimension=%d)", dim)
        _model, _dim = model, dim
    return _model


def dimension() -> int:
    if _dim is None:
        load_model()
    assert _dim is not None
    return _dim


def embed(texts: list[str]) -> np.ndarray:
    """Return L2-normalized float32 embeddings, shape (len(texts), dim)."""
    if not texts:
        return np.zeros((0, dimension()), dtype="float32")
    model = load_model()
    vecs = model.encode(
        texts,
        batch_size=64,
        convert_to_numpy=True,
        normalize_embeddings=True,   # so inner product == cosine similarity
        show_progress_bar=False,
    )
    return np.asarray(vecs, dtype="float32")


def embed_one(text: str) -> np.ndarray:
    return embed([text])[0]
