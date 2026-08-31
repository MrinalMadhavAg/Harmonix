"""Container entrypoint.

Deliberately runs a SINGLE uvicorn worker. FAISS and BM25 indexes are
in-process memory structures rebuilt from PostgreSQL at startup; with N
workers each worker would hold an independent copy and a write served by
worker 1 would be invisible to worker 2 until its next rebuild. For a
hackathon-scale dataset one worker is ample and removes a whole class of
"works on refresh, fails on refresh" bugs.
"""
from __future__ import annotations

import os

import uvicorn

if __name__ == "__main__":
    workers = int(os.getenv("UVICORN_WORKERS", "1"))
    if workers != 1:
        print(
            f"WARNING: UVICORN_WORKERS={workers}. In-memory FAISS/BM25 indexes are "
            "per-process and will diverge between workers.",
            flush=True,
        )
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        workers=workers,
        log_level=os.getenv("LOG_LEVEL", "info"),
    )
