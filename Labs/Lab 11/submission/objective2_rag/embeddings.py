"""
embeddings.py
-------------
Two interchangeable embedding backends for the RAG pipeline.

* `HFEmbeddings` - wraps sentence-transformers/all-MiniLM-L6-v2 via the
  LangChain `HuggingFaceEmbeddings` class. This is the default and is
  what the assignment's example code uses. Runs anywhere that can reach
  huggingface.co to download the model on first use (~80 MB). This is
  what will run on a typical developer laptop.

* `TfidfEmbeddings` - a pure-Python fallback using scikit-learn's
  TfidfVectorizer. Fits at ingest time, serializes the fitted vocabulary
  to `vectorizer.pkl` next to the vector store, and reloads it for
  queries. Requires no model download, so it works in restricted /
  air-gapped environments (like the Cowork sandbox used to render the
  transcripts in this submission).

Both backends expose the same two methods used by ingest.py and
rag_assistant.py:

    embed_documents(texts: list[str]) -> list[list[float]]
    embed_query(text: str)            -> list[float]

The ChromaDB collection is populated using explicit `embeddings=` at
add() time, so Chroma never has to call a built-in embedding function
(it has no network access in the sandbox).
"""

from __future__ import annotations

import pickle
from pathlib import Path
from typing import Protocol, runtime_checkable

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.preprocessing import normalize


@runtime_checkable
class EmbeddingBackend(Protocol):
    name: str
    dim: int

    def embed_documents(self, texts: list[str]) -> list[list[float]]: ...
    def embed_query(self, text: str) -> list[float]: ...


# ---------------------------------------------------------------------------
# TF-IDF backend
# ---------------------------------------------------------------------------

class TfidfEmbeddings:
    """Local, offline embedding using unigram+bigram TF-IDF with L2 norm.

    Must be fitted on the full corpus before use (`fit(documents)`), or
    loaded from a previously fitted pickle (`load(path)`).
    """

    name = "tfidf"

    def __init__(self, max_features: int = 2048, ngram_range=(1, 2)):
        self._vectorizer = TfidfVectorizer(
            max_features=max_features,
            ngram_range=ngram_range,
            lowercase=True,
            token_pattern=r"(?u)\b[A-Za-z0-9_./]{2,}\b",
        )
        self._fitted = False
        self.dim = 0

    def fit(self, documents: list[str]) -> "TfidfEmbeddings":
        m = self._vectorizer.fit_transform(documents)
        self._fitted = True
        self.dim = m.shape[1]
        return self

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if not self._fitted:
            raise RuntimeError("TfidfEmbeddings must be fit() before use.")
        m = self._vectorizer.transform(texts)
        m = normalize(m, norm="l2", axis=1)
        return m.toarray().astype(np.float32).tolist()

    def embed_query(self, text: str) -> list[float]:
        return self.embed_documents([text])[0]

    def save(self, path: Path) -> None:
        with path.open("wb") as f:
            pickle.dump(self._vectorizer, f)

    @classmethod
    def load(cls, path: Path) -> "TfidfEmbeddings":
        inst = cls()
        with path.open("rb") as f:
            inst._vectorizer = pickle.load(f)
        inst._fitted = True
        inst.dim = len(inst._vectorizer.get_feature_names_out())
        return inst


# ---------------------------------------------------------------------------
# HuggingFace backend (the assignment's default). Imported lazily so that
# the TF-IDF path works in environments that don't have torch installed.
# ---------------------------------------------------------------------------

class HFEmbeddings:
    """sentence-transformers/all-MiniLM-L6-v2 via LangChain.

    First call downloads ~80 MB from huggingface.co. Subsequent calls are
    cached under `~/.cache/huggingface/`.
    """

    name = "hf"

    def __init__(self, model_name: str = "sentence-transformers/all-MiniLM-L6-v2"):
        from langchain_community.embeddings import HuggingFaceEmbeddings  # lazy
        self._hf = HuggingFaceEmbeddings(model_name=model_name)
        self.dim = 384  # fixed for all-MiniLM-L6-v2

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return self._hf.embed_documents(texts)

    def embed_query(self, text: str) -> list[float]:
        return self._hf.embed_query(text)


def get_backend(name: str) -> EmbeddingBackend:
    name = name.lower()
    if name == "hf":
        return HFEmbeddings()
    if name == "tfidf":
        return TfidfEmbeddings()
    raise ValueError(f"Unknown embedding backend: {name!r}. Use 'hf' or 'tfidf'.")
