"""
ingest.py
---------
Build (or rebuild) the ChromaDB vector store from documents in
`knowledge_base/`. Run this once before starting rag_assistant.py.

Usage:
    python ingest.py                         # default: HF embeddings, knowledge_base/ -> chroma_db/
    python ingest.py --embeddings tfidf      # offline fallback (no downloads)
    python ingest.py --reset                 # wipe existing db and re-embed
"""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

import chromadb
from langchain_community.document_loaders import TextLoader
try:
    from langchain_text_splitters import RecursiveCharacterTextSplitter
except ImportError:  # fallback for older LangChain versions
    from langchain.text_splitter import RecursiveCharacterTextSplitter

from embeddings import TfidfEmbeddings, get_backend


HERE = Path(__file__).parent
DEFAULT_KB = HERE / "knowledge_base"
DEFAULT_DB = HERE / "chroma_db"
COLLECTION = "network_kb"


def load_documents(kb_dir: Path):
    docs = []
    allowed = {".txt", ".md", ".cfg", ".conf"}
    for path in sorted(kb_dir.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in allowed:
            continue
        for d in TextLoader(str(path), encoding="utf-8").load():
            d.metadata["source"] = path.name
            d.metadata["source_path"] = str(path.relative_to(kb_dir))
            docs.append(d)
    return docs


def chunk_documents(docs, chunk_size: int = 800, chunk_overlap: int = 150):
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        separators=["\n## ", "\n### ", "\n\n", "\n!", "\n", " ", ""],
    )
    return splitter.split_documents(docs)


def main() -> None:
    ap = argparse.ArgumentParser(description="Ingest network docs into Chroma.")
    ap.add_argument("--kb", type=Path, default=DEFAULT_KB)
    ap.add_argument("--db", type=Path, default=DEFAULT_DB)
    ap.add_argument("--embeddings", choices=["hf", "tfidf"], default="hf",
                    help="Embedding backend (default: hf).")
    ap.add_argument("--reset", action="store_true")
    ap.add_argument("--chunk-size", type=int, default=800)
    ap.add_argument("--chunk-overlap", type=int, default=150)
    args = ap.parse_args()

    if args.reset and args.db.exists():
        print(f"Wiping existing store at {args.db}")
        shutil.rmtree(args.db)
    args.db.mkdir(parents=True, exist_ok=True)

    print(f"Loading documents from {args.kb}")
    docs = load_documents(args.kb)
    if not docs:
        raise SystemExit(f"No documents found under {args.kb}")
    sources = sorted({d.metadata['source'] for d in docs})
    print(f"  loaded {len(docs)} document(s): {', '.join(sources)}")

    chunks = chunk_documents(docs, args.chunk_size, args.chunk_overlap)
    print(f"Split into {len(chunks)} chunk(s)")

    print(f"Initializing embedding backend: {args.embeddings}")
    backend = get_backend(args.embeddings)

    texts = [c.page_content for c in chunks]
    if isinstance(backend, TfidfEmbeddings):
        backend.fit(texts)
        backend.save(args.db / "vectorizer.pkl")
        print(f"  TF-IDF vocabulary size = {backend.dim}")

    print("Computing embeddings for all chunks...")
    vectors = backend.embed_documents(texts)

    print(f"Opening Chroma at {args.db}")
    client = chromadb.PersistentClient(path=str(args.db))
    # Drop existing collection of the same name so reingests don't pile up.
    try:
        client.delete_collection(COLLECTION)
    except Exception:
        pass
    coll = client.create_collection(
        COLLECTION,
        # Disable Chroma's own embedding function; we provide vectors ourselves.
        embedding_function=None,
    )

    ids = [f"chunk-{i:04d}" for i in range(len(chunks))]
    metadatas = [
        {
            "source": c.metadata.get("source", "<unknown>"),
            "source_path": c.metadata.get("source_path", ""),
            "chunk_index": i,
        }
        for i, c in enumerate(chunks)
    ]
    coll.add(ids=ids, documents=texts, metadatas=metadatas, embeddings=vectors)

    # Write a tiny manifest so rag_assistant knows which backend was used.
    manifest = {
        "backend": args.embeddings,
        "collection": COLLECTION,
        "num_chunks": len(chunks),
        "sources": sources,
        "chunk_size": args.chunk_size,
        "chunk_overlap": args.chunk_overlap,
    }
    (args.db / "manifest.json").write_text(json.dumps(manifest, indent=2))
    print(f"Done. {len(chunks)} chunks embedded and persisted.")
    print(f"Manifest: {json.dumps(manifest, indent=2)}")


if __name__ == "__main__":
    main()
