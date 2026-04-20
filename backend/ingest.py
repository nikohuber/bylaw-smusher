import os, sys, pdfplumber, chromadb, requests
from dotenv import load_dotenv

load_dotenv("../.env")

CHROMA_PATH     = os.getenv("CHROMA_PATH", "./chroma_data")
COLLECTION_NAME = os.getenv("CHROMA_COLLECTION", "bylaws")
OLLAMA_HOST     = os.getenv("OLLAMA_HOST", "http://localhost:11434")
EMBED_MODEL     = os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text")
CHUNK_SIZE      = int(os.getenv("CHUNK_SIZE", 500))
CHUNK_OVERLAP   = int(os.getenv("CHUNK_OVERLAP", 50))

def extract_text(pdf_path):
    pages = []
    with pdfplumber.open(pdf_path) as pdf:
        for i, page in enumerate(pdf.pages):
            text = page.extract_text()
            if text:
                pages.append({"page": i + 1, "text": text})
    return pages

def chunk_text(text, size=CHUNK_SIZE, overlap=CHUNK_OVERLAP):
    words = text.split()
    chunks, i = [], 0
    while i < len(words):
        chunks.append(" ".join(words[i:i + size]))
        i += size - overlap
    return chunks

def embed(text):
    r = requests.post(f"{OLLAMA_HOST}/api/embeddings",
                      json={"model": EMBED_MODEL, "prompt": text})
    r.raise_for_status()
    return r.json()["embedding"]

def ingest(pdf_path):
    client = chromadb.PersistentClient(path=CHROMA_PATH)
    col    = client.get_or_create_collection(COLLECTION_NAME)
    source = os.path.basename(pdf_path)
    pages  = extract_text(pdf_path)
    total  = 0
    for page in pages:
        for idx, chunk in enumerate(chunk_text(page["text"])):
            doc_id = f"{source}_p{page['page']}_c{idx}"
            col.add(
                ids=[doc_id],
                embeddings=[embed(chunk)],
                documents=[chunk],
                metadatas=[{"source": source, "page": page["page"]}]
            )
            total += 1
            print(f"\r  {total} chunks ingested...", end="")
    print(f"\nDone. {total} chunks from {source}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python ingest.py bylaws/your-bylaw.pdf")
        sys.exit(1)
    ingest(sys.argv[1])
