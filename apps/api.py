import os
import shutil
from datetime import datetime

from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import List, Optional

from .ingestion import ingest_document
from .embedding import upsert_chunks
from .retrieval import search
from .reranker import rerank
from .generation import generate_answer

#Writing Fast API Code

UPLOAD_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

app=FastAPI(
    title="RAG Classic Chatbot",
    description="A Classic RAG Chatbot",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Create Request and Response Models 

class IngestRequest(BaseModel):
    file_path:str 

class IngestResponse(BaseModel):
    file:str 
    chunks: int 
    message:str


class ChatRequest(BaseModel):
    question: str 
    use_reranker: bool=True 
    debug:bool =False 

class SourceChunk(BaseModel):
    id:str 
    score: float 
    source:str 
    pages:str 
    chunk_text:str 
    citation: str 

class ChatResponse(BaseModel):
    answer: str 
    sources: List[SourceChunk]
    retrieved: Optional[List[SourceChunk]]= None 
    reranked: Optional[List[SourceChunk]]= None 


class GenerateRequest(BaseModel):
    question: str 
    top_k: int=10
    top_n:int=5 
    use_reranker:bool =True 


class GenerateResponse(BaseModel):
    question:str 
    answer: str 
    sources: List[SourceChunk]
    pipeline:str 

class SearchRequest(BaseModel):
    query:str 
    top_k:Optional[int]=10
    user_reranker:bool=True 


# Add End Points

@app.get("/health")
def health_check():
    """Simple Health Check"""
    return {"status":"ok"}


@app.post("/ingest",response_model=IngestResponse)
def ingest_endpoint(req:IngestRequest):
    """Ingest a document, Extract Text, Chunk, Embed and Upsert to Pinecone"""
    try:
        records=ingest_document(req.file_path)
        upserted=upsert_chunks(records)

        return IngestResponse(
            file=req.file_path,
            chunks=upserted,
            message="Document Ingested Successfully"
        )
    
    except FileNotFoundError:
        raise HTTPException(status_code=404,detail="File Not Found")
    except ValueError as e:
        raise HTTPException(status_code=400,detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500,detail=str(e))
    
    
@app.post("/chat",response_model=ChatResponse)
def chat_endpoint(req:ChatRequest):
    """Full RAG Pipeline: User Question->Retrieve->Rerank->Generate Answer"""

    try:
        #Step 1: Fetch Relevant Results 
        retrieved_chunks=search(req.question)

        #Step 2: Rerank if enable

        if req.use_reranker:
            reranked_chunks=rerank(req.question)
            chunks=reranked_chunks

        else:
            chunks=retrieved_chunks 

        if not chunks:
            return ChatResponse(
                answer="I could not find any relevant information in the documents",
                sources=[]
            )
        
        # Step 3- Generate Answer with Citations 

        answer=generate_answer(req.question,chunks)

        def _to_source(c,idx):
            return SourceChunk(
                id=c["id"],
                score=c["score"],
                source=c["source"],
                pages=c.get("pages",""),
                chunk_text=c["chunk_text"][:200]+ "....",
                citation=f"[{idx}]"
            )
        
        sources= [_to_source(c,i) for i,c in enumerate(chunks,1)]

        debug_retrieved=None 
        debug_reranked=None 

        if req.debug:
            debug_retrieved=[_to_source(c,i) for i,c in enumerate(retrieved_chunks,1)]
            if req.use_reranker:
                debug_reranked=[_to_source(c,i)for i,c in enumerate(reranked_chunks,1)]

        
        return ChatResponse(
            answer=answer,
            sources=sources,
            retrieved=debug_retrieved,
            reranked=debug_reranked
        )
    
    except Exception as e:
        raise HTTPException(status_code=500,detail=str(e))


class UploadResponse(BaseModel):
    file: str
    chunks: int
    message: str


@app.post("/upload", response_model=UploadResponse)
async def upload_endpoint(file: UploadFile = File(...)):
    """Upload a file from browser, save it, then ingest into the RAG pipeline."""
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file provided")

    allowed_ext = (".pdf", ".txt", ".md")
    if not file.filename.lower().endswith(allowed_ext):
        raise HTTPException(status_code=400, detail=f"Unsupported file type. Allowed: {allowed_ext}")

    save_path = os.path.join(UPLOAD_DIR, file.filename)
    try:
        with open(save_path, "wb") as f:
            shutil.copyfileobj(file.file, f)

        records = ingest_document(save_path)
        upserted = upsert_chunks(records)

        return UploadResponse(
            file=file.filename,
            chunks=upserted,
            message="Document uploaded and ingested successfully",
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/documents")
def list_documents():
    """List all uploaded documents with metadata."""
    docs = []
    for f in os.listdir(UPLOAD_DIR):
        path = os.path.join(UPLOAD_DIR, f)
        if os.path.isfile(path):
            stat = os.stat(path)
            docs.append({
                "name": f,
                "size": stat.st_size,
                "uploaded_at": datetime.fromtimestamp(stat.st_mtime).isoformat(),
            })
    docs.sort(key=lambda d: d["uploaded_at"], reverse=True)
    return {"documents": docs}


@app.get("/documents/{filename}")
def serve_document(filename: str):
    """Serve an uploaded document file for preview."""
    path = os.path.join(UPLOAD_DIR, filename)
    if not os.path.isfile(path):
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(path, filename=filename)
