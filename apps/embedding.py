import time 
from typing import List, Dict 
from pinecone import Pinecone 
from .config import (
    PINECONE_API_KEY,
    PINECONE_INDEX_NAME,
    PINECONE_NAMESPACE,
    PINECONE_CLOUD,
    PINECONE_REGION,
    PINECONE_EMBED_MODEL
)


# Step1: Create Pinecone Client 

_pc= Pinecone(api_key=PINECONE_API_KEY)

def _get_or_create_index():

    if not _pc.has_index(PINECONE_INDEX_NAME):
        print(f"Creating Pinecone Index {PINECONE_INDEX_NAME} with integrated Embedding")

        _pc.create_index_for_model(
            name=PINECONE_INDEX_NAME,
            cloud=PINECONE_CLOUD,
            region=PINECONE_REGION,
            embed={
                "model": PINECONE_EMBED_MODEL,
                "field_map": {"text": "chunk_text"},
            },
        )

        print(" Waiting for index to be ready")

        while not _pc.describe_index(PINECONE_INDEX_NAME).status.get("ready",False):
            time.sleep(1)
        
        print("Index Created and Ready")

    return _pc.Index(PINECONE_INDEX_NAME)


def is_file_ingested(source:str)-> bool:

    index= _get_or_create_index()

    try:
        results= index.search(
            namespace= PINECONE_NAMESPACE,
            query={"top_k":1, "inputs": {"text": source}},
            fields=["source"]
        )

        for hit in results.get("result",{}).get("hits",[]):
            if hit.get("fields",{}).get("source")==source:
                return True 
    except Exception as e:
        print(f"Error checking existing records for source '{source}': {e}")
        return False

    return False


def upsert_chunks(records: List[Dict], batch_size:int=96)-> int:
    if not records:
        return 0
    
    source =records[0].get("source","")
    if source and is_file_ingested(source):
        print(f"{source} already exists in the Index. Skipping Ingestion")
        return 0

    index= _get_or_create_index()
    total=0 

    for i in range(0,len(records),batch_size):
        batch=records[i:i+batch_size]

        pinecone_records=[] 

        for rec in batch:
            pinecone_records.append(
                {
                    "_id": rec["id"],
                    "chunk_text": rec["chunk_text"],
                    "source": rec["source"],
                    "pages": rec.get("pages",""),
                }
            )
        
        index.upsert_records(PINECONE_NAMESPACE,pinecone_records)
        total+= len(pinecone_records)

    print(f"Upserted {total} records into {PINECONE_INDEX_NAME}")

    return total 


if __name__== "__main__":
    test_records=[
        {"id": "test::chunk-0","chunk_text": "Google Showed a growth of 26 percentage in last 3 months","source":"test_pdf"},
        {"id": "test::chunk-1","chunk_text": "Apple Showed a growth of 10 percentage in last 3 months","source":"test_pdf"},

    ]

    count=upsert_chunks(test_records)

    print(count)


        



  
