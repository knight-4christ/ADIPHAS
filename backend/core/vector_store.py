import os
import chromadb
from chromadb.config import Settings
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_chroma import Chroma
from sqlalchemy.orm import Session
from ..database import SessionLocal
from ..models import EBSAlert
from dotenv import load_dotenv

load_dotenv()

class ChromaManager:
    def __init__(self, persist_directory="./data/chroma_db"):
        self.persist_directory = persist_directory
        self.embeddings = GoogleGenerativeAIEmbeddings(
            model="models/gemini-embedding-001",
            google_api_key=os.getenv("GEMINI_API_KEY")
        )
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=1000,
            chunk_overlap=100
        )
        # Initialize vector store
        self.vector_store = Chroma(
            persist_directory=self.persist_directory,
            embedding_function=self.embeddings,
            collection_name="adiphas_knowledge"
        )

    def ingest_ebs_alerts(self, db: Session):
        """Fetch all verified EBS alerts and index them if not already present."""
        alerts = db.query(EBSAlert).filter(EBSAlert.verified == True).all()
        
        documents = []
        metadatas = []
        ids = []
        
        for alert in alerts:
            # Simple deduplication check by ID in metadatas if needed, 
            # but Chroma handles IDs. Use alert_id as vector ID.
            
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
            # No need for manual persist in newer Chroma versions, but good practice
            # self.vector_store.persist() 
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

    def hybrid_search(self, query: str, k: int = 3, threshold: float = 0.5):
        """
        Local-first search. If similarity score is low (high distance), 
        fall back to Tavily web search.
        """
        local_results = self.search_knowledge(query, k=k)
        
        # In Chroma, lower score usually means closer distance (higher similarity)
        # However, score values can vary by distance metric. 
        # For simplicity, we check if any local results exist.
        
        if local_results and local_results[0]['score'] < threshold:
            return {
                "source": "local_rag",
                "results": local_results
            }
        
        # Fallback to Tavily if key is available
        tavily_key = os.getenv("TAVILY_API_KEY")
        if tavily_key:
            try:
                from langchain_community.tools.tavily_search import TavilySearchResults
                web_search = TavilySearchResults(api_key=tavily_key)
                web_results = web_search.run(query)
                return {
                    "source": "web_search",
                    "results": web_results
                }
            except Exception as e:
                print(f"Web search failed: {e}")
                
        return {
            "source": "local_rag_fallback", # If no web key, return best local anyway
            "results": local_results
        }

# Singleton instance
vector_manager = ChromaManager()

def get_vector_manager():
    return vector_manager
