from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
FALLBACK_PATH = DATA_DIR / "vector_fallback.json"


class VectorStore:
    def __init__(self) -> None:
        self.mode = "fallback"
        self.collection = None
        self.encoder = None
        self._fallback_data = self._load_fallback()

        try:
            import chromadb
            from sentence_transformers import SentenceTransformer

            client = chromadb.PersistentClient(path=str(DATA_DIR / "chroma"))
            self.collection = client.get_or_create_collection(name="trustagent_context")
            self.encoder = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")
            self.mode = "chromadb"
        except Exception:
            self.mode = "fallback"

    def _load_fallback(self) -> list[dict[str, Any]]:
        if FALLBACK_PATH.exists():
            try:
                return json.loads(FALLBACK_PATH.read_text(encoding="utf-8"))
            except Exception:
                return []
        return []

    def _save_fallback(self) -> None:
        FALLBACK_PATH.write_text(json.dumps(self._fallback_data[-500:], ensure_ascii=True), encoding="utf-8")

    def _fallback_embed(self, text: str) -> list[float]:
        digest = hashlib.sha256(text.encode("utf-8")).digest()
        vec = np.frombuffer(digest * 8, dtype=np.uint8)[:128].astype(np.float32)
        norm = np.linalg.norm(vec) or 1.0
        return (vec / norm).tolist()

    def embed(self, text: str) -> list[float]:
        if self.encoder is not None:
            vec = self.encoder.encode(text)
            arr = np.array(vec, dtype=np.float32)
            norm = np.linalg.norm(arr) or 1.0
            return (arr / norm).tolist()
        return self._fallback_embed(text)

    def upsert(self, doc_id: str, text: str, metadata: dict[str, Any]) -> None:
        emb = self.embed(text)
        if self.mode == "chromadb" and self.collection is not None:
            self.collection.upsert(
                ids=[doc_id],
                documents=[text],
                metadatas=[metadata],
                embeddings=[emb],
            )
            return

        self._fallback_data.append({"id": doc_id, "text": text, "metadata": metadata, "embedding": emb})
        self._save_fallback()

    def query(self, text: str, top_k: int = 3) -> list[dict[str, Any]]:
        emb = np.array(self.embed(text), dtype=np.float32)

        if self.mode == "chromadb" and self.collection is not None:
            res = self.collection.query(query_embeddings=[emb.tolist()], n_results=top_k)
            ids = res.get("ids", [[]])[0]
            docs = res.get("documents", [[]])[0]
            metas = res.get("metadatas", [[]])[0]
            dists = res.get("distances", [[]])[0]
            out: list[dict[str, Any]] = []
            for idx, doc_id in enumerate(ids):
                out.append(
                    {
                        "id": doc_id,
                        "text": docs[idx] if idx < len(docs) else "",
                        "metadata": metas[idx] if idx < len(metas) else {},
                        "distance": float(dists[idx]) if idx < len(dists) else None,
                    }
                )
            return out

        scored: list[tuple[float, dict[str, Any]]] = []
        for row in self._fallback_data:
            other = np.array(row.get("embedding", []), dtype=np.float32)
            if other.size == 0:
                continue
            sim = float(np.dot(emb, other) / ((np.linalg.norm(emb) or 1.0) * (np.linalg.norm(other) or 1.0)))
            scored.append((sim, row))

        scored.sort(key=lambda x: x[0], reverse=True)
        out = []
        for sim, row in scored[:top_k]:
            out.append({"id": row["id"], "text": row["text"], "metadata": row.get("metadata", {}), "similarity": round(sim, 4)})
        return out


vector_store = VectorStore()
