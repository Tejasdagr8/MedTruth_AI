"""
Shared FastAPI dependencies — singletons for clients and stores.
Loaded once at startup and injected into route handlers.
"""

import os
from functools import lru_cache

from src.retrieval.pubmed_client import PubMedClient
from src.retrieval.europepmc_client import EuropePMCClient
from src.retrieval.who_cochrane_client import WHOClient, CochraneClient
from src.vector_store.chroma_store import MedTruthVectorStore
from src.rag.rag_chain import MedTruthRAGChain
from src.rag.graph_pipeline import MedTruthPipeline


@lru_cache(maxsize=1)
def get_pubmed_client() -> PubMedClient:
    return PubMedClient(
        api_key=os.getenv("NCBI_API_KEY"),
        max_results=int(os.getenv("PUBMED_MAX_RESULTS", "8")),
    )


@lru_cache(maxsize=1)
def get_europepmc_client() -> EuropePMCClient:
    return EuropePMCClient(max_results=int(os.getenv("EUROPEPMC_MAX_RESULTS", "5")))


@lru_cache(maxsize=1)
def get_who_client() -> WHOClient:
    return WHOClient(max_results=3)


@lru_cache(maxsize=1)
def get_cochrane_client() -> CochraneClient:
    return CochraneClient(max_results=3)


@lru_cache(maxsize=1)
def get_vector_store() -> MedTruthVectorStore:
    return MedTruthVectorStore()


@lru_cache(maxsize=1)
def get_rag_chain() -> MedTruthRAGChain:
    return MedTruthRAGChain()


@lru_cache(maxsize=1)
def get_pipeline() -> MedTruthPipeline:
    return MedTruthPipeline(
        vector_store=get_vector_store(),
        rag_chain=get_rag_chain(),
    )
