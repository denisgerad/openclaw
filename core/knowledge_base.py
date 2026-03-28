"""
core/knowledge_base.py
───────────────────────
KnowledgeBase: ChromaDB-backed knowledge store per project.

Embedding strategy (no SDK dependency issues):
  Production:  MistralEmbedding — calls Mistral API via requests,
               uses mistral-embed model, same API key as the rest of OpenClaw.
  Offline/test: LocalTFIDFEmbedding — pure Python, no network, no downloads.
               Activated when MISTRAL_API_KEY is absent or OPENCLAW_KB_OFFLINE=1.

HIL contract:
  propose_save() NEVER writes to ChromaDB.
  execute_save() writes ONLY after human approval.
  search() is always immediate (read-only).
"""

import os
import json
import math
import hashlib
import requests
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import chromadb
from chromadb import EmbeddingFunction, Documents, Embeddings

DEDUP_THRESHOLD    = 0.92
CHUNK_SIZE         = 800
CHUNK_OVERLAP      = 100
DEFAULT_COLLECTION = "knowledge"
MAX_SEARCH_RESULTS = 8


# ── Embedding functions ───────────────────────────────────────────────────────

class LocalTFIDFEmbedding(EmbeddingFunction):
    """
    Offline TF-IDF embedding — pure Python, zero network calls.
    Used when MISTRAL_API_KEY is absent or OPENCLAW_KB_OFFLINE=1.
    Produces normalised 256-dim vectors; cosine similarity works correctly.
    """
    _DIM = 256

    def __init__(self): pass  # explicit to silence chromadb deprecation

    def name(self) -> str:
        return "local_tfidf"

    def get_config(self) -> dict:
        return {"name": self.name(), "dim": self._DIM}

    def __call__(self, input: Documents) -> Embeddings:
        vecs = []
        for text in input:
            words = text.lower().split()
            counts = Counter(words)
            vec = [0.0] * self._DIM
            for word, cnt in counts.items():
                idx = int(hashlib.md5(word.encode()).hexdigest(), 16) % self._DIM
                vec[idx] += math.log(1 + cnt)
            norm = math.sqrt(sum(x * x for x in vec)) or 1.0
            vecs.append([x / norm for x in vec])
        return vecs


class MistralEmbedding(EmbeddingFunction):
    """
    Production embedding via Mistral API (mistral-embed model).
    Uses the same MISTRAL_API_KEY already configured for the orchestrator.
    Falls back silently to LocalTFIDFEmbedding on API error.
    """
    _MODEL = "mistral-embed"
    _URL   = "https://api.mistral.ai/v1/embeddings"
    _BATCH = 32   # max texts per request

    def __init__(self):
        self._api_key = os.getenv("MISTRAL_API_KEY", "")
        self._fallback = LocalTFIDFEmbedding()

    def name(self) -> str:
        return "mistral_embed"

    def get_config(self) -> dict:
        return {"name": self.name(), "model": self._MODEL}

    def __call__(self, input: Documents) -> Embeddings:
        if not self._api_key:
            return self._fallback(input)
        try:
            all_embeddings = []
            for i in range(0, len(input), self._BATCH):
                batch = list(input[i: i + self._BATCH])
                resp = requests.post(
                    self._URL,
                    headers={
                        "Authorization": f"Bearer {self._api_key}",
                        "Content-Type":  "application/json",
                    },
                    json={"model": self._MODEL, "input": batch},
                    timeout=30,
                )
                resp.raise_for_status()
                data = resp.json()
                all_embeddings.extend([item["embedding"] for item in data["data"]])
            return all_embeddings
        except Exception:
            return self._fallback(input)


def _make_embedding_fn() -> EmbeddingFunction:
    """Return the right embedding function based on environment."""
    offline = os.getenv("OPENCLAW_KB_OFFLINE", "").lower() in ("1", "true", "yes")
    has_key = bool(os.getenv("MISTRAL_API_KEY", ""))
    if offline or not has_key:
        return LocalTFIDFEmbedding()
    return MistralEmbedding()


# ── Data classes ──────────────────────────────────────────────────────────────

@dataclass
class KBDocument:
    doc_id:       str
    content:      str
    source:       str
    title:        str
    tags:         list[str]
    timestamp:    str
    project:      str
    chunk_index:  int = 0
    total_chunks: int = 1

    def to_metadata(self) -> dict:
        return {
            "source":       self.source,
            "title":        self.title,
            "tags":         json.dumps(self.tags),
            "timestamp":    self.timestamp,
            "project":      self.project,
            "chunk_index":  self.chunk_index,
            "total_chunks": self.total_chunks,
        }


@dataclass
class KBSearchResult:
    doc_id:    str
    content:   str
    source:    str
    title:     str
    tags:      list[str]
    timestamp: str
    distance:  float

    @property
    def similarity_pct(self) -> int:
        return max(0, int((1 - self.distance / 2) * 100))


@dataclass
class KBSaveProposal:
    project_name:    str
    title:           str
    source:          str
    content:         str
    tags:            list[str]
    chunks:          list[str]
    near_duplicates: list[KBSearchResult]
    is_duplicate:    bool
    decision:        str = ""
    edited_content:  str = ""
    edited_tags:     list[str] = field(default_factory=list)


# ── KnowledgeBase ─────────────────────────────────────────────────────────────

class KnowledgeBase:
    """
    Per-project ChromaDB knowledge base.
    HIL-gated writes: propose_save() → human review → execute_save().
    """

    def __init__(self, project_name: str, kb_path: Path):
        self.project     = project_name
        self.kb_path     = kb_path
        self.kb_path.mkdir(parents=True, exist_ok=True)
        self._embed_fn   = _make_embedding_fn()
        self._client     = chromadb.PersistentClient(path=str(self.kb_path))
        self._collection = self._client.get_or_create_collection(
            name=DEFAULT_COLLECTION,
            embedding_function=self._embed_fn,
            metadata={"hnsw:space": "cosine"},
        )

    # ── Stats ─────────────────────────────────────────────────────────────────

    def count(self) -> int:
        return self._collection.count()

    def list_sources(self) -> list[dict]:
        if self._collection.count() == 0:
            return []
        results = self._collection.get(include=["metadatas"])
        seen = {}
        for meta in results["metadatas"]:
            src = meta.get("source", "")
            if src and src not in seen:
                seen[src] = {
                    "source":    src,
                    "title":     meta.get("title", ""),
                    "timestamp": meta.get("timestamp", ""),
                    "tags":      json.loads(meta.get("tags", "[]")),
                }
        return list(seen.values())

    # ── Read: search (no HIL) ─────────────────────────────────────────────────

    def search(
        self,
        query:      str,
        n_results:  int = MAX_SEARCH_RESULTS,
        tag_filter: Optional[str] = None,
    ) -> list[KBSearchResult]:
        if self._collection.count() == 0:
            return []
        try:
            kwargs = dict(
                query_texts=[query],
                n_results=min(n_results, self._collection.count()),
                include=["documents", "metadatas", "distances"],
            )
            if tag_filter:
                kwargs["where"] = {"tags": {"$contains": tag_filter}}
            raw = self._collection.query(**kwargs)
        except Exception:
            raw = self._collection.query(
                query_texts=[query],
                n_results=min(n_results, self._collection.count()),
                include=["documents", "metadatas", "distances"],
            )
        return [
            KBSearchResult(
                doc_id    = "",
                content   = doc,
                source    = meta.get("source", ""),
                title     = meta.get("title", ""),
                tags      = json.loads(meta.get("tags", "[]")),
                timestamp = meta.get("timestamp", ""),
                distance  = dist,
            )
            for doc, meta, dist in zip(
                raw["documents"][0],
                raw["metadatas"][0],
                raw["distances"][0],
            )
        ]

    # ── HIL Step 1: Propose ───────────────────────────────────────────────────

    def propose_save(
        self,
        content: str,
        title:   str,
        source:  str,
        tags:    Optional[list[str]] = None,
    ) -> KBSaveProposal:
        tags   = tags or []
        chunks = self._chunk_text(content)
        dupes  = self._check_duplicates(content)
        is_dup = any(r.similarity_pct >= int(DEDUP_THRESHOLD * 100) for r in dupes)
        return KBSaveProposal(
            project_name    = self.project,
            title           = title,
            source          = source,
            content         = content,
            tags            = tags,
            chunks          = chunks,
            near_duplicates = dupes,
            is_duplicate    = is_dup,
        )

    # ── HIL Step 2: Execute ───────────────────────────────────────────────────

    def execute_save(self, proposal: KBSaveProposal) -> int:
        content = proposal.edited_content or proposal.content
        tags    = proposal.edited_tags    or proposal.tags
        chunks  = self._chunk_text(content)
        now     = datetime.now(timezone.utc).isoformat()

        ids, docs, metas = [], [], []
        for i, chunk in enumerate(chunks):
            doc_id = self._make_id(proposal.source, i)
            ids.append(doc_id)
            docs.append(chunk)
            metas.append(KBDocument(
                doc_id=doc_id, content=chunk,
                source=proposal.source, title=proposal.title,
                tags=tags, timestamp=now, project=self.project,
                chunk_index=i, total_chunks=len(chunks),
            ).to_metadata())

        self._collection.upsert(ids=ids, documents=docs, metadatas=metas)
        return len(chunks)

    def delete_by_source(self, source: str) -> int:
        results = self._collection.get(where={"source": source}, include=["metadatas"])
        ids = results.get("ids", [])
        if ids:
            self._collection.delete(ids=ids)
        return len(ids)

    def get_by_source(self, source: str) -> str:
        """Return the full concatenated text for all chunks of a given source."""
        results = self._collection.get(
            where={"source": source},
            include=["documents", "metadatas"],
        )
        if not results["documents"]:
            return ""
        paired = sorted(
            zip(results["metadatas"], results["documents"]),
            key=lambda x: x[0].get("chunk_index", 0),
        )
        return "\n".join(doc for _, doc in paired)

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _chunk_text(self, text: str) -> list[str]:
        text = text.strip()
        if len(text) <= CHUNK_SIZE:
            return [text]
        chunks, start = [], 0
        while start < len(text):
            chunks.append(text[start: start + CHUNK_SIZE])
            start += CHUNK_SIZE - CHUNK_OVERLAP
        return chunks

    def _check_duplicates(self, content: str) -> list[KBSearchResult]:
        if self._collection.count() == 0:
            return []
        return [r for r in self.search(content[:500], n_results=3) if r.similarity_pct >= 70]

    @staticmethod
    def _make_id(source: str, chunk_index: int) -> str:
        h = hashlib.md5(f"{source}:{chunk_index}".encode()).hexdigest()[:12]
        return f"chunk_{h}_{chunk_index}"
