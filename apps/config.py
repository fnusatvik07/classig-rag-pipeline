import os
from dotenv import load_dotenv
load_dotenv()

# Base directory (project root)
BASE_DIR: str = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# API Keys

PINECONE_API_KEY:str = os.getenv("PINECONE_API_KEY", "")
OPENAI_API_KEY:str = os.getenv("OPENAI_API_KEY", "")

# Chunking Settings

CHUNK_SIZE: int =512  #Characters 
CHUNK_OVERLAP: int =64 #Overlap

# Pinecone Settings 

PINECONE_INDEX_NAME: str = "myragchatbot"
PINECONE_NAMESPACE: str = "mydocments"
PINECONE_CLOUD:str = "aws"
PINECONE_REGION: str = "us-east-1"
PINECONE_EMBED_MODEL: str = "multilingual-e5-large"
PINECONE_RERANK_MODEL: str= "bge-reranker-v2-m3"

# Retrieval Settings

TOP_K: int=10 
RERANK_TOP_N:int=5

# Generation Settings 

OPENAI_MODEL: str = "gpt-4o-mini"
MAX_TOKENS:int =1024
TEMPERATURE: float =0.2

# Cache Settings

CACHE_BACKEND: str = os.getenv("CACHE_BACKEND", "sqlite")                          # "sqlite" or "redis"
CACHE_ENABLED: bool = os.getenv("CACHE_ENABLED", "true").lower() == "true"
EXACT_CACHE_TTL: int = int(os.getenv("EXACT_CACHE_TTL", "604800"))                  # 7 days in seconds
SEMANTIC_CACHE_TTL: int = int(os.getenv("SEMANTIC_CACHE_TTL", "604800"))             # 7 days in seconds
SEMANTIC_CACHE_THRESHOLD: float = float(os.getenv("SEMANTIC_CACHE_THRESHOLD", "0.92"))
RETRIEVAL_CACHE_TTL: int = int(os.getenv("RETRIEVAL_CACHE_TTL", "86400"))            # 1 day in seconds
RETRIEVAL_CACHE_THRESHOLD: float = float(os.getenv("RETRIEVAL_CACHE_THRESHOLD", "0.85"))
DATABASE_PATH: str = os.getenv("DATABASE_PATH", os.path.join(BASE_DIR, "data", "rag_cache.db"))
REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")
OPENAI_EMBED_MODEL: str = os.getenv("OPENAI_EMBED_MODEL", "text-embedding-3-small")