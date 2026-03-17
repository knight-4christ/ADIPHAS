import os
import json
import logging
import threading
import time
import numpy as np
from dotenv import load_dotenv
from sqlalchemy.orm import Session
from ..database import SessionLocal
from ..models import EBSAlert

load_dotenv()
logger = logging.getLogger(__name__)

class GeminiAPIEmbeddings:
    """
    Uses Google's text-embedding-004 model via the GenAI SDK.
    Bypasses all local torch/onnx DLL issues (WinError 1114) on Windows by computing remotely.
    """
    def __init__(self, api_key=None):
        from google import genai
        if not api_key:
            api_key = os.getenv("GEMINI_API_KEY")
        self.client = genai.Client(api_key=api_key)
        self.model_name = "gemini-embedding-001"

    def embed_documents(self, texts):
        if not texts: return []
        
        all_embeddings = []
        batch_size = 50 
        
        logger.info(f"[GeminiEmbed] Embedding {len(texts)} documents (API)...")
        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]
            success = False
            for attempt in range(2): # Reduced retries for faster fallback
                try:
                    response = self.client.models.embed_content(
                        model=self.model_name,
                        contents=batch,
                    )
                    all_embeddings.extend([e.values for e in response.embeddings])
                    success = True
                    break
                except Exception as e:
                    logger.warning(f"[GeminiEmbed] Batch failed (attempt {attempt+1}): {e}")
                    time.sleep(1)
            
            if not success:
                # Ultimate Fallback Header
                from .model_config import _embed_via_openrouter
                logger.warning(f"[GeminiEmbed] Triggering OpenRouter Fallback for batch...")
                or_embs = _embed_via_openrouter(batch)
                if or_embs:
                    all_embeddings.extend(or_embs)
                else:
                    logger.error(f"[GeminiEmbed] EVERY embedding path exhausted. Zero-padding.")
                    all_embeddings.extend([[0.0] * 3072 for _ in batch])
                
        return all_embeddings

    def embed_query(self, text):
        if not text: return [0.0] * 3072
        for attempt in range(2):
            try:
                response = self.client.models.embed_content(
                    model=self.model_name,
                    contents=text,
                )
                return response.embeddings[0].values
            except Exception as e:
                logger.warning(f"[GeminiEmbed] Query failed (attempt {attempt+1}): {e}")
                time.sleep(1)
        
        # OpenRouter fallback for single query
        from .model_config import _embed_via_openrouter
        or_embs = _embed_via_openrouter(text)
        if or_embs and len(or_embs) > 0:
            return or_embs[0]
            
        return [0.0] * 3072

class TitanVectorEngine:
    """
    A robust, Pure-Python/Numpy Vector Store for high-stability RAG on Windows.
    Bypasses native ChromaDB/SQLite-VSS freezes entirely. 
    Optimal for health situational awareness datasets (10k-50k vectors).
    """
    def __init__(self, persist_path="./data/vector_store.json"):
        self.persist_path = persist_path
        self.data = {"documents": [], "embeddings": [], "metadatas": [], "ids": []}
        self._lock = threading.Lock()
        self._load()

    def _load(self):
        if os.path.exists(self.persist_path):
            try:
                with open(self.persist_path, 'r') as f:
                    self.data = json.load(f)
                logger.info(f"[TitanVector] Loaded {len(self.data['ids'])} vectors from disk.")
            except Exception as e:
                logger.error(f"[TitanVector] Load failed: {e}. Starting fresh.")
        else:
            os.makedirs(os.path.dirname(self.persist_path), exist_ok=True)

    def _save(self):
        with open(self.persist_path, 'w') as f:
            json.dump(self.data, f)

    def add_texts(self, texts, embeddings, metadatas, ids):
        with self._lock:
            self.data["documents"].extend(texts)
            self.data["embeddings"].extend(embeddings)
            self.data["metadatas"].extend(metadatas)
            self.data["ids"].extend(ids)
            self._save()

    def similarity_search(self, query_emb, k=3):
        with self._lock:
            if not self.data["embeddings"]:
                return []
            
            # Use Numpy for fast cosine similarity calculation
            vectors = np.array(self.data["embeddings"])
            query = np.array(query_emb)
            
            # Cosine similarity: (A dot B) / (norm(A) * norm(B))
            dot_product = np.dot(vectors, query)
            norms = np.linalg.norm(vectors, axis=1) * np.linalg.norm(query)
            # Clip to avoid division by zero or precision errors
            similarities = dot_product / (norms + 1e-9)
            
            # Get top K indices
            top_k_indices = np.argsort(similarities)[::-1][:k]
            
            results = []
            for idx in top_k_indices:
                results.append({
                    "content": self.data["documents"][idx],
                    "metadata": self.data["metadatas"][idx],
                    "score": float(similarities[idx])
                })
            return results

class ChromaManager:
    """Wrapper that maintains the legacy API but uses TitanVector for 100% stability."""
    def __init__(self, persist_directory="./data/chroma_db"):
        self.embeddings = GeminiAPIEmbeddings()
        # Titan uses a single file for persistence, avoiding SQLite DLL issues
        self.vector_store = TitanVectorEngine(persist_path=os.path.join(persist_directory, "titan_store.json"))
        self._lock = threading.Lock()

    def ingest_ebs_alerts(self, db: Session):
        """Fetch UN-VECTORIZED alerts and index them via Titan."""
        with self._lock:
            alerts = db.query(EBSAlert).filter(EBSAlert.is_vectorized == False).all()
            if not alerts: return 0

            texts = []
            metadatas = []
            ids = []

            for alert in alerts:
                content = f"Source: {alert.source}\nDisease: {alert.disease}\nLocation: {alert.location_text}\nSummary: {alert.summary}"
                texts.append(content)
                metadatas.append({
                    "alert_id": alert.alert_id,
                    "source": alert.source,
                    "disease": alert.disease or "Unknown",
                    "location": alert.location_text
                })
                ids.append(str(alert.alert_id))

            if texts:
                logger.info(f"[VectorEngine] TitanVector embedding {len(texts)} new alerts...")
                embs = self.embeddings.embed_documents(texts)
                self.vector_store.add_texts(texts, embs, metadatas, ids)
                
                for alert in alerts:
                    alert.is_vectorized = True
                db.commit()
                logger.info(f"[VectorEngine] TitanVector successfully indexed {len(texts)} alerts.")
                return len(texts)
            return 0

    def search_knowledge(self, query: str, k: int = 3):
        """Perform semantic search using Titan engine."""
        logger.info(f"[VectorEngine] Semantic search initiated.")
        query_emb = self.embeddings.embed_query(str(query))
        return self.vector_store.similarity_search(query_emb, k=k)

    def hybrid_search(self, query: str, k: int = 3, threshold: float = 0.5, force_combine: bool = False):
        local_results = self.search_knowledge(query, k=k)
        
        # Simple RAG fallback logic
        if not force_combine and local_results and local_results[0]['score'] > threshold:
             return {"source": "local_rag", "results": local_results}

        tavily_key = os.getenv("TAVILY_API_KEY")
        if tavily_key:
            try:
                from langchain_community.tools.tavily_search import TavilySearchResults
                web_search = TavilySearchResults(api_key=tavily_key)
                web_results = web_search.run(query)
                if force_combine:
                    return {"source": "combined", "results": local_results + web_results}
                return {"source": "web_search", "results": web_results}
            except Exception as e:
                logger.error(f"Web search failed: {e}")

        return {"source": "local_rag_fallback", "results": local_results}

# Singleton instance
vector_manager = None

def get_vector_manager():
    global vector_manager
    if vector_manager is None:
        vector_manager = ChromaManager()
    return vector_manager
