# Lab 11 — AI/ML for Network Engineering

**Author:** Atul Anand (atul@nexthop.ai)
**Course:** CSCI 5380 — Network Virtualization and Orchestration, Spring 2026
**Instructor:** Prof. Levi Perigo, Ph.D.

This submission implements the two **mandatory** objectives:

1. **Objective 1** — Agentic Network Operations with MCP (`objective1_mcp/`)
2. **Objective 2** — Network Engineering RAG Assistant (`objective2_rag/`)

Full write-ups, per-query explanations, and reflections are in
`Lab_11_Submission.md` (and the same content in `Lab_11_Submission.docx`).

Raw transcripts of every test run (JSON + colorized HTML) are in
`transcripts/`.

---

## Quick start

```bash
# 1. Create and activate a virtualenv
python3 -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure your Anthropic API key
cp .env.example .env
# edit .env and set ANTHROPIC_API_KEY=sk-ant-...

# 4. Objective 1 — run the MCP agent against the 5 required queries
cd objective1_mcp
python mcp_client.py --suite

# 5. Objective 2 — ingest the knowledge base, then run the RAG suite
cd ../objective2_rag
python ingest.py --embeddings hf           # or: --embeddings tfidf
python rag_assistant.py --suite
```

A single top-level runner is also provided:

```bash
python run_all.py       # executes both suites and writes transcripts/
```

---

## Submission layout

```
submission/
├── README.md                              ← this file
├── requirements.txt                       ← pinned Python deps
├── .env.example                           ← template for ANTHROPIC_API_KEY
├── run_all.py                             ← helper to run both suites
├── Lab_11_Submission.md                   ← narrative write-up (Obj 1 + Obj 2)
├── Lab_11_Submission.docx                 ← same content as Word document
│
├── objective1_mcp/
│   ├── network_data.py                    ← simulated device state (3 devices,
│   │                                       with deliberate anomalies)
│   ├── mcp_network_server.py              ← FastMCP server exposing 7 tools
│   └── mcp_client.py                      ← agentic loop: Claude ↔ MCP stdio
│
├── objective2_rag/
│   ├── knowledge_base/                    ← 7 source documents
│   │   ├── router1_running_config.txt
│   │   ├── router2_running_config.txt
│   │   ├── firewall1_running_config.txt
│   │   ├── switch1_running_config.txt
│   │   ├── switch2_running_config.txt
│   │   ├── network_design_doc.md
│   │   └── runbook_bgp_idle_troubleshooting.md
│   ├── embeddings.py                      ← HF + TF-IDF backends
│   ├── ingest.py                          ← load / chunk / embed / persist
│   └── rag_assistant.py                   ← retrieve + ground + answer
│
└── transcripts/
    ├── obj1_transcripts.json / .html      ← 5 MCP queries, full trace
    ├── obj2_transcripts.json / .html      ← 5 RAG queries, full trace
    └── *_console.log                      ← raw captured stdout
```

---

## Notes on the embedding backend

The assignment's example code uses `langchain_community.embeddings.HuggingFaceEmbeddings`,
which under the hood pulls `sentence-transformers/all-MiniLM-L6-v2` from
huggingface.co on first use (~80 MB download). That is the **default** and
what any normal developer machine will run (`python ingest.py`).

The transcripts shipped in this submission were generated inside a
restricted sandbox that could **not** reach `huggingface.co` or Chroma's
model S3 bucket, so I added a second backend — scikit-learn
`TfidfVectorizer` — that needs zero downloads. Both backends expose the
same interface (`embed_documents`, `embed_query`) and both populate the
same ChromaDB collection. Pick either with `--embeddings hf` or
`--embeddings tfidf`.

The write-up section on Query 3 of Objective 2 discusses what changes
between lexical (TF-IDF) and semantic (MiniLM) retrieval for this
corpus.

---

## Models / cost

All runs use `claude-sonnet-4-5` (Anthropic). Total API cost for the
entire test suite (10 queries, ~30 tool calls, ~30 embedded chunks) is
under $0.05 — well inside the free-tier credit on a new Anthropic
Console account.

The key used to generate the transcripts in this submission was
disposable and has been revoked. Reviewers who want to re-run the
suite end-to-end should supply their own key in `.env`.
