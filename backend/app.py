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
