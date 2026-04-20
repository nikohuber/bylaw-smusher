# Zoning Bylaw Analyzer — Project Context

## What this project is

A self-hosted web application that lets users ask plain-language questions about municipal
zoning bylaws and receive accurate, document-grounded answers. The app ingests zoning bylaw
PDFs, chunks and embeds them into a local vector store, and uses a locally-hosted LLM to
answer queries with retrieved context (RAG architecture).

Guiding principle: keep it as simple as possible. No containers, no cloud services, no
infrastructure cost. Everything runs as plain processes on one machine.

---

## Hardware

**Server:** Dell R720
- OS: Ubuntu Server 22.04 LTS
- All services run as plain processes — no Docker required

**GPU (current / prototyping):** AMD Radeon RX Vega 56
- 8 GB HBM2 VRAM
- CRITICAL: always set `HSA_OVERRIDE_GFX_VERSION=9.0.0` — Vega 56 is not auto-detected
  by ROCm without this. Set it in shell and in Ollama's systemd service file.
- Model constraint: 7B models at full precision, quantized up to ~13B (Q4)
- Use `llama3:8b` to start

**GPU (future upgrade):** NVIDIA Tesla P40
- 24 GB VRAM, standard CUDA stack
- When installed: swap `OLLAMA_MODEL=llama3:8b` to `llama3:70b-instruct-q4_K_M` in `.env`
- No other code changes needed

---

## Stack — lean prototype edition

| Layer | Technology | Why |
|-------|-----------|-----|
| Model serving | Ollama (native) | GPU access, OpenAI-compatible API, simple |
| Embeddings | `nomic-embed-text` via Ollama | No separate embedding service needed |
| Vector store | ChromaDB (in-process) | Pure Python library, no container, stores to disk |
| PDF ingestion | `pdfplumber` | Text-based PDFs only; add pytesseract later if needed |
| Backend | Flask (single file) | Minimal boilerplate, runs with `python app.py` |
| Frontend | Vite + React | Fast dev server, no Node server, `npm run dev` |

**No Docker. No Docker Compose. No cloud services.**

---

## Project structure

```
zoning-app/
├── CLAUDE.md                  ← you are here
├── .env                       ← local config (never commit)
├── .gitignore
│
├── backend/
│   ├── app.py                 ← entire Flask API (single file)
│   ├── ingest.py              ← PDF → chunks → ChromaDB (run once per bylaw doc)
│   ├── requirements.txt
│   └── bylaws/                ← drop bylaw PDFs here
│       └── .gitkeep
│
└── frontend/
    ├── package.json
    ├── vite.config.ts
    └── src/
        ├── main.tsx
        ├── App.tsx
        └── components/
            ├── QuestionInput.tsx
            ├── AnswerCard.tsx
            └── UploadButton.tsx
```

---

## Environment variables

Create `.env` at project root:

```env
# Ollama
OLLAMA_HOST=http://localhost:11434
OLLAMA_MODEL=llama3:8b
OLLAMA_EMBED_MODEL=nomic-embed-text

# ChromaDB — persists vector data to this local path
CHROMA_PATH=./chroma_data
CHROMA_COLLECTION=bylaws

# Flask
FLASK_PORT=8000
CHUNK_SIZE=500
CHUNK_OVERLAP=50
TOP_K=5

# Frontend (Vite reads VITE_ prefix)
VITE_API_URL=http://localhost:8000
```

---

## Ollama setup (Vega 56 / ROCm)

```bash
# Install Ollama
curl -fsSL https://ollama.com/install.sh | sh

# CRITICAL: set before any ollama commands
export HSA_OVERRIDE_GFX_VERSION=9.0.0

# Pull models
ollama pull llama3:8b
ollama pull nomic-embed-text

# Verify GPU is being used (should show GPU memory, not CPU)
ollama run llama3:8b "hello"
ollama ps   # confirm model loaded on GPU not CPU
```

Add to Ollama systemd service so it persists across reboots:
```bash
sudo systemctl edit ollama
```
```ini
[Service]
Environment="HSA_OVERRIDE_GFX_VERSION=9.0.0"
Environment="OLLAMA_HOST=0.0.0.0:11434"
```

---

## Backend — `backend/requirements.txt`

```
flask
flask-cors
chromadb
pdfplumber
requests
python-dotenv
```

Install:
```bash
cd backend && pip install -r requirements.txt
```

---

## Backend — `backend/ingest.py`

Run once per bylaw PDF to populate ChromaDB.

```python
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
```

---

## Backend — `backend/app.py`

```python
import os, json, requests, chromadb
from flask import Flask, request, jsonify, stream_with_context, Response
from flask_cors import CORS
from dotenv import load_dotenv

load_dotenv("../.env")

OLLAMA_HOST     = os.getenv("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_MODEL    = os.getenv("OLLAMA_MODEL", "llama3:8b")
EMBED_MODEL     = os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text")
CHROMA_PATH     = os.getenv("CHROMA_PATH", "./chroma_data")
COLLECTION_NAME = os.getenv("CHROMA_COLLECTION", "bylaws")
TOP_K           = int(os.getenv("TOP_K", 5))
PORT            = int(os.getenv("FLASK_PORT", 8000))

app    = Flask(__name__)
CORS(app)
chroma = chromadb.PersistentClient(path=CHROMA_PATH)
col    = chroma.get_or_create_collection(COLLECTION_NAME)

PROMPT_TEMPLATE = """You are a plain-language zoning bylaw assistant helping homeowners
and contractors understand local zoning rules. Answer based only on the provided bylaw
excerpts. Be specific and practical. Cite section numbers when present. If the excerpts
don't contain enough information, say so clearly rather than guessing. Never frame your
answer as legal advice.

BYLAW EXCERPTS:
{context}

QUESTION:
{question}

ANSWER:"""

def embed(text):
    r = requests.post(f"{OLLAMA_HOST}/api/embeddings",
                      json={"model": EMBED_MODEL, "prompt": text})
    r.raise_for_status()
    return r.json()["embedding"]

def retrieve(question):
    results = col.query(query_embeddings=[embed(question)], n_results=TOP_K)
    return results["documents"][0], results["metadatas"][0]

@app.get("/health")
def health():
    try:
        requests.get(f"{OLLAMA_HOST}/api/tags", timeout=2).raise_for_status()
        ollama_ok = True
    except Exception:
        ollama_ok = False
    return jsonify({"ollama": "ok" if ollama_ok else "error",
                    "chroma": "ok",
                    "chunks_indexed": col.count()})

@app.post("/ask")
def ask():
    q = (request.json or {}).get("question", "").strip()
    if not q:
        return jsonify({"error": "question required"}), 400

    docs, metas = retrieve(q)
    context     = "\n\n---\n\n".join(docs)
    prompt      = PROMPT_TEMPLATE.format(context=context, question=q)
    sources     = [{"page": m.get("page"), "source": m.get("source"),
                    "preview": d[:120] + "..."} for d, m in zip(docs, metas)]

    def generate():
        r = requests.post(f"{OLLAMA_HOST}/api/generate",
                          json={"model": OLLAMA_MODEL, "prompt": prompt, "stream": True},
                          stream=True)
        for line in r.iter_lines():
            if line:
                chunk = json.loads(line)
                if not chunk.get("done"):
                    yield chunk.get("response", "")

    resp = Response(stream_with_context(generate()), mimetype="text/plain")
    resp.headers["X-Sources"] = json.dumps(sources)
    return resp

@app.get("/collections")
def collections():
    return jsonify({"count": col.count(), "name": COLLECTION_NAME})

if __name__ == "__main__":
    print(f"Starting on http://localhost:{PORT}")
    print(f"Model: {OLLAMA_MODEL}  |  Chunks indexed: {col.count()}")
    app.run(port=PORT, debug=True)
```

---

## Frontend setup

```bash
cd frontend
npm create vite@latest . -- --template react-ts
npm install
```

Proxy API calls in `vite.config.ts` to avoid CORS in dev:
```ts
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        rewrite: path => path.replace(/^\/api/, '')
      }
    }
  }
})
```

---

## Running the app

Three terminals:

```bash
# Terminal 1 — Ollama (if not running as a service)
HSA_OVERRIDE_GFX_VERSION=9.0.0 ollama serve

# Terminal 2 — Flask backend
cd backend && python app.py

# Terminal 3 — Vite frontend
cd frontend && npm run dev
```

Open `http://localhost:5173`

---

## Ingesting a bylaw PDF

```bash
cd backend
python ingest.py bylaws/burlington-vt-zoning.pdf
```

Re-run any time you add a new PDF. ChromaDB deduplicates by ID so re-ingesting
the same file is safe. Check chunk count after:
```bash
curl http://localhost:8000/collections
```

---

## Known constraints

**Vega 56 / ROCm**
- `HSA_OVERRIDE_GFX_VERSION=9.0.0` must be set or Ollama silently falls back to CPU
- Run `ollama ps` to confirm the model loaded on GPU, not CPU
- 8B model inference is roughly 10–20 tok/s on Vega 56 — acceptable for a prototype

**ChromaDB**
- Stores data in `./chroma_data/` — back this up if you ingest many documents
- In-process: only one backend process can write at a time (fine for a prototype)
- Migration to Qdrant later requires only swapping the client calls

**Scanned PDFs**
- `pdfplumber` only works on text-based PDFs
- If extraction returns empty strings, the PDF is image-based
- Fix: add `pytesseract` as an OCR fallback in `ingest.py`

**Upgrading to P40**
- Install CUDA drivers, remove `HSA_OVERRIDE_GFX_VERSION` from systemd
- Set `OLLAMA_MODEL=llama3:70b-instruct-q4_K_M` in `.env`
- Restart Ollama — everything else is identical

---

## What good output looks like

> "For a single-story residential structure in an R-1 zone, the minimum front setback
> is 25 feet, side setbacks are 8 feet each, and rear setback is 20 feet (Section 4.3.2).
> Maximum building height is 35 feet. You will need a building permit before breaking
> ground. If your lot is under 7,500 sq ft, confirm lot coverage does not exceed 40% of
> total lot area (Section 4.3.5)."

If answers are vague or hallucinated (no section references, generic statements), the
retrieval step is failing — check chunk count at `/collections` and confirm the model
loaded on GPU with `ollama ps`.

---

## Planned features (not yet built)

- Address lookup → auto-detect zoning district
- Permit checklist generator (structured output mode)
- Upload UI (currently ingest via CLI only)
- Multi-municipality dropdown
- Bylaw amendment diff tracking
- Production hardening (gunicorn, nginx, auth)