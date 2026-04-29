"""
ChromaDB vector store with BioBERT-compatible embeddings.
Handles ingestion, similarity search, and MEDEVA-weighted re-ranking.
"""

import json
import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

import chromadb
from chromadb.config import Settings
from sentence_transformers import SentenceTransformer

CHROMA_PERSIST_DIR = os.getenv("CHROMA_PERSIST_DIR", "./data/chroma_db")
EMBEDDING_MODEL = os.getenv(
    "EMBEDDING_MODEL", "pritamdeka/BioBERT-mnli-snli-scinli-scitail-mednli-stsb"
)
COLLECTION_NAME = "medtruth_docs"


class MedTruthVectorStore:
    """
    Persistent ChromaDB collection backed by BioBERT sentence embeddings.
    Supports ingestion of unified retrieval docs and semantic similarity search.
    """

    def __init__(
        self,
        persist_dir: str = CHROMA_PERSIST_DIR,
        embedding_model: str = EMBEDDING_MODEL,
        collection_name: str = COLLECTION_NAME,
    ):
        self._embedder = SentenceTransformer(embedding_model)
        self._client = chromadb.PersistentClient(
            path=persist_dir,
            settings=Settings(anonymized_telemetry=False),
        )
        self._collection = self._client.get_or_create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine"},
        )

    def _embed(self, texts: list[str]) -> list[list[float]]:
        embeddings = self._embedder.encode(texts, normalize_embeddings=True)
        return embeddings.tolist()

    def upsert_documents(self, docs: list[dict]) -> int:
        """
        Ingest retrieval documents into the vector store.
        Skips duplicates (upsert by ID).
        Returns count of new documents added.
        """
        if not docs:
            return 0

        ids = [doc["id"] for doc in docs]
        texts = [doc["text"] for doc in docs]
        metadatas = []
        for doc in docs:
            meta = doc.get("metadata", {})
            # ChromaDB requires all metadata values to be str/int/float/bool
            sanitized = {}
            for k, v in meta.items():
                if isinstance(v, (str, int, float, bool)):
                    sanitized[k] = v
                elif isinstance(v, list):
                    sanitized[k] = json.dumps(v)
                elif v is None:
                    sanitized[k] = ""
                else:
                    sanitized[k] = str(v)
            metadatas.append(sanitized)

        embeddings = self._embed(texts)
        self._collection.upsert(
            ids=ids,
            documents=texts,
            embeddings=embeddings,
            metadatas=metadatas,
        )
        return len(ids)

    def search(
        self,
        query: str,
        top_k: int = 10,
        source_filter: Optional[list[str]] = None,
    ) -> list[dict]:
        """
        Semantic search returning top_k documents with similarity scores.
        Optionally filter by source (e.g. ['pubmed', 'cochrane']).
        """
        query_embedding = self._embed([query])[0]

        where_clause = None
        if source_filter:
            if len(source_filter) == 1:
                where_clause = {"source": source_filter[0]}
            else:
                where_clause = {"$or": [{"source": s} for s in source_filter]}

        results = self._collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k,
            where=where_clause,
            include=["documents", "metadatas", "distances"],
        )

        docs = []
        ids = results["ids"][0]
        documents = results["documents"][0]
        metadatas = results["metadatas"][0]
        distances = results["distances"][0]

        for i, doc_id in enumerate(ids):
            # ChromaDB returns cosine distance; convert to similarity
            similarity = 1.0 - distances[i]
            meta = metadatas[i]
            # Deserialize list fields
            for k, v in meta.items():
                if isinstance(v, str) and v.startswith("["):
                    try:
                        meta[k] = json.loads(v)
                    except json.JSONDecodeError:
                        logger.warning("Failed to deserialize metadata field %r", k, exc_info=True)
            docs.append({
                "id": doc_id,
                "text": documents[i],
                "metadata": meta,
                "similarity": round(similarity, 4),
            })

        return docs

    def search_with_medeva(
        self,
        query: str,
        top_k: int = 10,
        medeva_weight: float = 0.4,
    ) -> list[dict]:
        """
        Hybrid search: combines semantic similarity with pre-computed MEDEVA scores.
        final_score = (1 - medeva_weight) * similarity + medeva_weight * medeva_total
        """
        from src.ranking.medeva_scorer import score_document

        raw_results = self.search(query, top_k=top_k * 2)

        for doc in raw_results:
            if "medeva" not in doc:
                medeva = score_document(doc)
                doc["medeva"] = medeva.to_dict()
            sim = doc["similarity"]
            medeva_total = doc["medeva"]["total"]
            doc["hybrid_score"] = (
                (1 - medeva_weight) * sim + medeva_weight * medeva_total
            )

        ranked = sorted(raw_results, key=lambda d: d["hybrid_score"], reverse=True)
        return ranked[:top_k]

    def get_semantic_similarities(
        self, query: str, docs: list[dict]
    ) -> list[float]:
        """Return cosine similarity of query against a pre-fetched doc list."""
        if not docs:
            return []
        query_emb = self._embed([query])[0]
        doc_texts = [d["text"] for d in docs]
        doc_embs = self._embed(doc_texts)

        import numpy as np
        q = np.array(query_emb)
        similarities = []
        for emb in doc_embs:
            d = np.array(emb)
            sim = float(np.dot(q, d) / (np.linalg.norm(q) * np.linalg.norm(d) + 1e-9))
            similarities.append(round(sim, 4))
        return similarities

    def count(self) -> int:
        return self._collection.count()

    def delete_collection(self):
        self._client.delete_collection(COLLECTION_NAME)
