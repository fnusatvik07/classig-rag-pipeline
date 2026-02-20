import os 
from dotenv import load_dotenv 
load_dotenv() 


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