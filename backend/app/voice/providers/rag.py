"""ChromaDB-backed vector store for per-agent RAG retrieval.

Design goals
------------
* One ChromaDB collection per agent (collection name = agent_id string).
* OpenAI text-embedding-3-small (fast, cheap, 1536-dim) for all embeddings.
* Persistent local storage under ./chroma_db (zero external deps in dev).
* async-first: all retrieval runs in a thread-pool executor so it never
  blocks the asyncio event loop (critical — the pipeline is fully async).
* Warm-up: call warm_agent(agent_id) at call start to pre-load the
  collection into ChromaDB's in-process cache → zero cold-start latency
  on the first actual search.
"""

from __future__ import annotations

import asyncio
import os
from functools import lru_cache
from typing import TYPE_CHECKING

from app.core.logging import get_logger

if TYPE_CHECKING:
    import chromadb

log = get_logger(__name__)

_CHROMA_DIR = os.environ.get("CHROMA_DIR", "./chroma_db")
_EMBED_MODEL = "text-embedding-3-small"
_TOP_K_DEFAULT = 3

# Sentinel so we import chromadb + openai only once, lazily.
_client: "chromadb.PersistentClient | None" = None
_embed_fn = None


def _get_client():
    global _client
    if _client is None:
        import chromadb

        _client = chromadb.PersistentClient(path=_CHROMA_DIR)
    return _client


def _get_embed_fn():
    global _embed_fn
    if _embed_fn is None:
        from chromadb.utils.embedding_functions import OpenAIEmbeddingFunction
        from app.core.config import settings

        api_key = settings.openai_api_key or os.environ.get("OPENAI_API_KEY", "")
        _embed_fn = OpenAIEmbeddingFunction(
            api_key=api_key,
            model_name=_EMBED_MODEL,
        )
    return _embed_fn


def _collection_name(agent_id: str) -> str:
    # ChromaDB collection names must be 3-63 chars, alphanumeric + hyphens.
    return f"agent-{agent_id}"


def _get_collection(agent_id: str):
    client = _get_client()
    return client.get_or_create_collection(
        name=_collection_name(agent_id),
        embedding_function=_get_embed_fn(),
        metadata={"hnsw:space": "cosine"},
    )


# ── Public async interface ─────────────────────────────────────────────────

async def add_chunks(agent_id: str, chunks: list[dict]) -> None:
    """Upsert text chunks into the agent's collection (background thread).

    Each chunk dict: {"id": str, "text": str, "metadata": dict}
    """
    def _run():
        coll = _get_collection(agent_id)
        ids = [c["id"] for c in chunks]
        texts = [c["text"] for c in chunks]
        metas = [c.get("metadata", {}) for c in chunks]
        coll.upsert(ids=ids, documents=texts, metadatas=metas)
        log.info("rag.chunks_added", agent_id=agent_id, count=len(chunks))

    await asyncio.get_event_loop().run_in_executor(None, _run)


async def delete_document_chunks(agent_id: str, doc_id: str) -> None:
    """Remove all chunks that belong to a specific document."""
    def _run():
        coll = _get_collection(agent_id)
        coll.delete(where={"doc_id": doc_id})

    await asyncio.get_event_loop().run_in_executor(None, _run)


async def search_agent_knowledge(agent_id: str, query: str, top_k: int = _TOP_K_DEFAULT) -> str:
    """Retrieve the most relevant chunks for *query* and format for LLM context.

    Returns a formatted string ready to inject into the LLM context.
    Returns a short "not found" message when the collection is empty or
    the query has no good match (distance > 0.7).
    """
    def _run() -> list[dict]:
        try:
            coll = _get_collection(agent_id)
            if coll.count() == 0:
                return []
            results = coll.query(
                query_texts=[query],
                n_results=min(top_k, coll.count()),
                include=["documents", "metadatas", "distances"],
            )
            out = []
            docs = results.get("documents", [[]])[0]
            metas = results.get("metadatas", [[]])[0]
            dists = results.get("distances", [[]])[0]
            for doc, meta, dist in zip(docs, metas, dists):
                if dist <= 0.75:   # cosine distance threshold
                    out.append({"text": doc, "source": meta.get("filename", ""), "dist": dist})
            return out
        except Exception as exc:  # noqa: BLE001
            log.warning("rag.search_error", error=str(exc))
            return []

    import time as _time
    t0 = _time.monotonic()
    loop = asyncio.get_event_loop()
    chunks = await loop.run_in_executor(None, _run)
    latency_ms = round((_time.monotonic() - t0) * 1000)

    if not chunks:
        log.info("rag.searched", query=query[:60], hits=0, latency_ms=latency_ms)
        return "No relevant information found in the knowledge base."

    log.info("rag.searched", query=query[:60], hits=len(chunks), latency_ms=latency_ms)
    lines = ["Relevant information from uploaded documents:\n"]
    for i, c in enumerate(chunks, 1):
        src = f" [{c['source']}]" if c["source"] else ""
        lines.append(f"{i}.{src} {c['text']}")
    return "\n".join(lines)


async def warm_agent(agent_id: str) -> None:
    """Pre-load the agent's collection into ChromaDB's in-memory cache."""
    def _run():
        try:
            coll = _get_collection(agent_id)
            _ = coll.count()   # forces collection load
        except Exception as exc:  # noqa: BLE001
            log.debug("rag.warm_skip", error=str(exc))

    await asyncio.get_event_loop().run_in_executor(None, _run)


async def warm_embeddings() -> None:
    """Pre-warm the OpenAI embedding HTTP connection pool.

    Eliminates the 1-2 s cold-start TLS handshake on the first speculative
    RAG call. Run once during pipeline.start() in parallel with STT/TTS setup.
    """
    def _run() -> None:
        try:
            fn = _get_embed_fn()
            fn(["warmup"])    # single dummy call — establishes TCP+TLS to OpenAI
            log.info("rag.embeddings_warmed")
        except Exception as exc:  # noqa: BLE001
            log.debug("rag.embed_warm_skip", error=str(exc))

    await asyncio.get_event_loop().run_in_executor(None, _run)


async def count_chunks(agent_id: str) -> int:
    """Return the number of chunks indexed for an agent."""
    def _run() -> int:
        try:
            return _get_collection(agent_id).count()
        except Exception:  # noqa: BLE001
            return 0

    return await asyncio.get_event_loop().run_in_executor(None, _run)
