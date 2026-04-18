"""
rag_assistant.py
----------------
Network-engineering RAG assistant. Retrieves the most relevant chunks
from the ChromaDB knowledge base built by ingest.py, constructs a
context-grounded prompt, and asks Claude for an answer with citations.

Usage:
    python rag_assistant.py "What IP is on Gi0/0/1 of Router1?"
    python rag_assistant.py --suite
    python rag_assistant.py                       # interactive REPL
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

import chromadb
from anthropic import Anthropic
from rich.console import Console
from rich.panel import Panel

from embeddings import TfidfEmbeddings, get_backend


HERE = Path(__file__).parent
DEFAULT_DB = HERE / "chroma_db"
COLLECTION = "network_kb"


REQUIRED_QUERIES: list[str] = [
    "What IP address is assigned to GigabitEthernet0/0/1 on Router1?",
    "What OSPF areas are configured in the network, and which networks are advertised into each?",
    "What ACLs are applied to the outside interface on Firewall1?",
    "How does traffic from VLAN 10 reach the internet? Walk me through the path.",
    # Unanswerable from the knowledge base - tests anti-hallucination behavior.
    "What brand and part number of optical SFP is installed in Router1 Gi0/0/3?",
]


SYSTEM_PROMPT = (
    "You are a senior network engineer assistant. You answer operational "
    "and design questions about the NextHop enterprise network.\n\n"
    "RULES (non-negotiable):\n"
    "1. Answer ONLY from the <context> passages provided. Do not invoke "
    "general knowledge about Cisco, BGP, OSPF, etc., except to interpret "
    "the exact text you see.\n"
    "2. Every factual claim must be followed by a citation of the form "
    "[source: <filename>]. Use the source filename exactly as it appears "
    "in each <passage> tag's `source=` attribute.\n"
    "3. If the context does not contain the answer, reply exactly: "
    "\"I don't have enough information in the provided documents to answer "
    "that.\" Do not guess, do not speculate, do not fill gaps from training.\n"
    "4. Use proper networking terminology (interface names, IP/mask, ASN, "
    "VLAN ID, ACL names). Keep answers operator-friendly and concise."
)


def _load_env_file() -> None:
    if os.getenv("ANTHROPIC_API_KEY"):
        return
    for p in [Path.cwd() / ".env", Path(__file__).parent / ".env",
              Path(__file__).parent.parent / ".env",
              Path(__file__).parent.parent.parent / ".env"]:
        if p.is_file():
            for line in p.read_text().splitlines():
                if line.strip().startswith("ANTHROPIC_API_KEY="):
                    os.environ["ANTHROPIC_API_KEY"] = line.split("=", 1)[1].strip()
                    return


class RagAssistant:
    def __init__(
        self,
        db_dir: Path = DEFAULT_DB,
        model: str = "claude-sonnet-4-5",
        k: int = 4,
        console: Console | None = None,
    ):
        if not db_dir.exists():
            raise FileNotFoundError(
                f"Vector store not found at {db_dir}. Run `python ingest.py` first."
            )
        manifest_path = db_dir / "manifest.json"
        if not manifest_path.exists():
            raise FileNotFoundError(
                f"No manifest.json in {db_dir}. Re-run ingest.py."
            )
        self.manifest = json.loads(manifest_path.read_text())
        self.console = console or Console()

        backend_name = self.manifest.get("backend", "hf")
        if backend_name == "tfidf":
            self.backend = TfidfEmbeddings.load(db_dir / "vectorizer.pkl")
        else:
            self.backend = get_backend(backend_name)

        self.anthropic = Anthropic()
        self.model = model
        self.k = k
        self.client = chromadb.PersistentClient(path=str(db_dir))
        self.coll = self.client.get_collection(COLLECTION, embedding_function=None)

    def retrieve(self, query: str) -> list[dict[str, Any]]:
        qvec = self.backend.embed_query(query)
        r = self.coll.query(
            query_embeddings=[qvec],
            n_results=self.k,
            include=["documents", "metadatas", "distances"],
        )
        results: list[dict[str, Any]] = []
        for doc, meta, dist in zip(
            r["documents"][0], r["metadatas"][0], r["distances"][0]
        ):
            results.append({
                "source": meta.get("source", "<unknown>"),
                "distance": float(dist),
                "content": doc,
            })
        return results

    def ask(self, query: str) -> dict[str, Any]:
        self.console.rule(f"[bold cyan]QUERY[/bold cyan]: {query}")
        chunks = self.retrieve(query)

        self.console.print(
            f"[yellow]Retrieved {len(chunks)} chunk(s) (top-{self.k}) using "
            f"backend={self.manifest['backend']}[/yellow]"
        )
        for i, c in enumerate(chunks, 1):
            preview = c["content"][:320] + ("..." if len(c["content"]) > 320 else "")
            self.console.print(Panel(
                preview,
                title=f"chunk {i} · [bold]{c['source']}[/bold] · distance={c['distance']:.3f}",
                border_style="magenta",
            ))

        context_block = "\n\n".join(
            f"<passage source=\"{c['source']}\">\n{c['content']}\n</passage>"
            for c in chunks
        )
        user_msg = (
            f"<context>\n{context_block}\n</context>\n\n"
            f"<question>{query}</question>\n\n"
            "Answer using only the context above, with [source: <file>] citations."
        )

        resp = self.anthropic.messages.create(
            model=self.model,
            max_tokens=900,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_msg}],
        )
        answer = "".join(b.text for b in resp.content if b.type == "text").strip()
        self.console.print(Panel(answer, title="ANSWER", border_style="green"))
        return {
            "query": query,
            "retrieved": chunks,
            "answer": answer,
            "usage": {
                "input_tokens": resp.usage.input_tokens,
                "output_tokens": resp.usage.output_tokens,
            },
        }


def main() -> None:
    ap = argparse.ArgumentParser(description="Network RAG assistant.")
    ap.add_argument("query", nargs="?")
    ap.add_argument("--suite", action="store_true",
                    help="Run the 5 required test queries.")
    ap.add_argument("--model", default="claude-sonnet-4-5")
    ap.add_argument("--k", type=int, default=4)
    ap.add_argument("--db", type=Path, default=DEFAULT_DB,
                    help="Path to the Chroma persistence directory.")
    ap.add_argument("--save-json")
    ap.add_argument("--save-html")
    args = ap.parse_args()

    _load_env_file()
    if not os.getenv("ANTHROPIC_API_KEY"):
        print("ERROR: ANTHROPIC_API_KEY is not set. See README.md.", file=sys.stderr)
        sys.exit(2)

    console = Console(record=args.save_html is not None)
    asst = RagAssistant(db_dir=args.db, model=args.model, k=args.k, console=console)

    transcripts: list[dict[str, Any]] = []
    if args.suite:
        queries = REQUIRED_QUERIES
    elif args.query:
        queries = [args.query]
    else:
        console.print("Interactive mode. Ctrl-D to exit.", style="dim")
        while True:
            try:
                q = console.input("[bold]you>[/bold] ")
            except EOFError:
                break
            if q.strip():
                transcripts.append(asst.ask(q))
        queries = []

    for q in queries:
        transcripts.append(asst.ask(q))

    if args.save_json:
        Path(args.save_json).write_text(json.dumps(transcripts, indent=2))
        console.print(f"[green]Saved -> {args.save_json}[/green]")
    if args.save_html:
        console.save_html(args.save_html)
        console.print(f"[green]Saved -> {args.save_html}[/green]")


if __name__ == "__main__":
    main()
