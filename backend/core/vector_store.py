import os
import logging
import chromadb
# from langchain_text_splitters import RecursiveCharacterTextSplitter # REPLACED: Avoids torch/transformers import
from langchain_chroma import Chroma
from sqlalchemy.orm import Session
from ..database import SessionLocal
from ..models import EBSAlert
from dotenv import load_dotenv

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
        self.model_name = "text-embedding-004"

    def embed_documents(self, texts):
        if not texts: return []
        try:
            response = self.client.models.embed_content(
                model=self.model_name,
                contents=texts,
            )
            # GenAI returns a list of representations.
            return [e.values for e in response.embeddings]
        except Exception as e:
            logger.error(f"[GeminiAPIEmbeddings] Batch embedding failed: {e}")
            # text-embedding-004 returns 768 dimensions by default. Return fallback vector to prevent Chroma crashing
            return [[0.0] * 768 for _ in texts]

    def embed_query(self, text):
        if not text: return [0.0] * 768
        try:
            response = self.client.models.embed_content(
                model=self.model_name,
                contents=text,
            )
            return response.embeddings[0].values
        except Exception as e:
            logger.error(f"[GeminiAPIEmbeddings] Query embedding failed: {e}")
            return [0.0] * 768

class LocalTextSplitter:
    """A simple Character-based splitter that does NOT depend on torch or transformers."""
    def __init__(self, chunk_size=1000, chunk_overlap=100):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

    def split_text(self, text: str):
        chunks = []
        if not text: return chunks
        start = 0
        while start < len(text):
            end = min(start + self.chunk_size, len(text))
            chunks.append(text[start:end])
            if end == len(text): break
            start += (self.chunk_size - self.chunk_overlap)
        return chunks

    def create_documents(self, texts, metadatas=None):
        from langchain.docstore.document import Document
        docs = []
        for i, text in enumerate(texts):
            chunks = self.split_text(text)
            for chunk in chunks:
                meta = metadatas[i] if metadatas else {}
                docs.append(Document(page_content=chunk, metadata=meta))
        return docs

class ChromaManager:
    def __init__(self, persist_directory="./data/chroma_db"):
        self.persist_directory = persist_directory

        # --- HIGH QUALITY AI EMBEDDINGS ---
        try:
            self.embeddings = GeminiAPIEmbeddings(os.getenv("GEMINI_API_KEY"))
            logger.info("[VectorEngine] Initialized Gemini text-embedding-004 API embeddings for high-quality semantic routing.")
        except Exception as e:
            logger.error(f"[VectorEngine] Failed to initialize Gemini APIs Embeddings: {e}")
            raise e

        self.text_splitter = LocalTextSplitter(
            chunk_size=1000,
            chunk_overlap=100
        )
        # Initialize vector store with explicit collection creation check
        try:
            self._chroma_client = chromadb.PersistentClient(path=self.persist_directory)
            # Ensure the collection exists
            self._chroma_client.get_or_create_collection("adiphas_v2")
            
            self.vector_store = Chroma(
                client=self._chroma_client,
                embedding_function=self.embeddings,
                collection_name="adiphas_v2",
            )
        except Exception as e:
            logger.error(f"[VectorEngine] Failed to initialize Chroma: {e}")
            raise e

    def ingest_ebs_alerts(self, db: Session):
        """Fetch only UN-VECTORIZED alerts and index them. Marks them after success."""
        # Only process new, un-vectorized alerts (not all verified alerts)
        alerts = db.query(EBSAlert).filter(
            EBSAlert.is_vectorized == False
        ).all()

        if not alerts:
            return 0

        documents = []
        metadatas = []
        ids = []

        for alert in alerts:
            content = f"Source: {alert.source}\nDisease: {alert.disease}\nLocation: {alert.location_text}\nSummary: {alert.summary}\nFull Text: {alert.text}"

            chunks = self.text_splitter.split_text(content)
            for i, chunk in enumerate(chunks):
                documents.append(chunk)
                metadatas.append({
                    "alert_id": alert.alert_id,
                    "source": alert.source,
                    "disease": alert.disease or "Unknown",
                    "location": alert.location_text,
                    "timestamp": alert.timestamp.isoformat() if alert.timestamp else ""
                })
                ids.append(f"{alert.alert_id}_{i}")

        if documents:
            self.vector_store.add_texts(
                texts=documents,
                metadatas=metadatas,
                ids=ids
            )

            # Mark all processed alerts as vectorized
            for alert in alerts:
                alert.is_vectorized = True
            db.commit()

            logger.info(f"[VectorEngine] Embedded {len(documents)} chunks from {len(alerts)} new alerts (locally, 0 API tokens).")
            return len(documents)
        return 0

    def search_knowledge(self, query: str, k: int = 3):
        """Perform semantic search on the local knowledge base."""
        results = self.vector_store.similarity_search_with_score(query, k=k)

        formatted_results = []
        for doc, score in results:
            formatted_results.append({
                "content": doc.page_content,
                "metadata": doc.metadata,
                "score": float(score)
            })
        return formatted_results

    def hybrid_search(self, query: str, k: int = 3, threshold: float = 0.5, force_combine: bool = False):
        """
        Local-first search. If similarity score is low (high distance), 
        fall back to Tavily web search. If force_combine is True, merges both.
        """
        local_results = self.search_knowledge(query, k=k)

        if not force_combine:
            # In Chroma, lower score usually means closer distance (higher similarity)
            if local_results and local_results[0]['score'] < threshold:
                return {
                    "source": "local_rag",
                    "results": local_results
                }

        web_results = []
        # Fallback (or combine) to Tavily if key is available
        tavily_key = os.getenv("TAVILY_API_KEY")
        if tavily_key:
            try:
                from langchain_community.tools.tavily_search import TavilySearchResults
                web_search = TavilySearchResults(api_key=tavily_key)
                web_results = web_search.run(query)
            except Exception as e:
                logger.error(f"Web search failed: {e}")

        if force_combine:
            return {
                "source": "combined",
                "results": local_results + web_results
            }

        if web_results:
            return {
                "source": "web_search",
                "results": web_results
            }

        return {
            "source": "local_rag_fallback",
            "results": local_results
        }

# Singleton instance
vector_manager = ChromaManager()

def get_vector_manager():
    return vector_manager
