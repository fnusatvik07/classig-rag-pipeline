# Objective- Take any PDF , Extract Text out of it and Create Chunks

import os 
import re 
from typing import List, Dict 
from pypdf import PdfReader
from .config import CHUNK_SIZE, CHUNK_OVERLAP


# Step 1- Text Extraction 

def extract_pages_from_pdf(file_path:str)->List[Dict]:
    reader=PdfReader(file_path)

    pages=[] 

    for i, page in enumerate(reader.pages):
        text=page.extract_text() or ""
        if text.strip():
            pages.append({"page": i+1,"text": text})
    
    return pages 

def extract_pages_from_txt(file_path:str)->List[Dict]:
    with open(file_path,"r",encoding="utf-8") as f:
        return [{"page":1,"text":f.read()}]
    

def extract_pages(file_path:str)->List[Dict]:
    ext=os.path.splitext(file_path)[1].lower()

    if ext == ".pdf":
        return extract_pages_from_pdf(file_path)
    
    elif ext in (".txt",".md"):
        return extract_pages_from_txt(file_path)
    
    else:
        raise ValueError(f"Unsupported File Type: {ext}")


# result=extract_pages("/Users/datasense/Desktop/rag-pipeline-classic/docs/Apple_Q24.pdf")


# Step 2: Chunking 



def clean_text(text:str)->str:
    text=re.sub(r"\s+"," ",text)
    return text.strip()

def chunk_pages(
        pages: List[Dict],
        chunk_size: int = CHUNK_SIZE,
        overlap:int = CHUNK_OVERLAP
)-> List[Dict]:
    
    full_text=""
    char_to_page: List[int]=[]

    for p in pages:
        cleaned=clean_text(p["text"])

        if cleaned:
            if full_text:
                full_text+= " "
                char_to_page.append(p["page"])
            full_text += cleaned
            char_to_page.extend([p["page"]]* len(cleaned))
    
    chunks: List[Dict]= [] 

    start=0
    while start<len(full_text):
        end=min(start+chunk_size,len(full_text))
        chunk=full_text[start:end].strip() 

        if chunk:
            page_set=sorted(set(char_to_page[start:end]))
            chunks.append({"chunk_text": chunk, "pages":page_set})
            
        start+= chunk_size - overlap 
    
    return chunks


            

def ingest_document(file_path :str)-> List[Dict]:
    file_name=os.path.basename(file_path)

    pages=extract_pages(file_path)
    chunks= chunk_pages(pages)

    records=[]

    for idx, chunk in enumerate(chunks):
        page_str=",".join(str(p) for p in chunk["pages"])
        records.append(
            {
                "id": f"{file_name}:: chunk-{idx+1}",
                "chunk_text": chunk["chunk_text"],
                "source": file_name,
                "pages": page_str,

            }
        )
    
    print(f"Ingested '{file_name}'-- {len(records)} chunks")
    return records



