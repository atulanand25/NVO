"""
run_all.py
----------
Convenience runner that executes both objectives end-to-end. Meant for
a clean clone + fresh virtualenv.

Usage:
    python run_all.py
    python run_all.py --embeddings tfidf   # offline mode
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path


HERE = Path(__file__).parent
TRANSCRIPTS = HERE / "transcripts"


def run(cmd: list[str], cwd: Path) -> None:
    print(f"\n$ (cd {cwd.name} && {' '.join(cmd)})")
    subprocess.run(cmd, cwd=cwd, check=True)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--embeddings", choices=["hf", "tfidf"], default="hf")
    ap.add_argument("--model", default="claude-sonnet-4-5")
    args = ap.parse_args()

    if not os.getenv("ANTHROPIC_API_KEY"):
        # Search HERE, then walk up a few parent directories for a .env file.
        candidates = [HERE, *HERE.parents[:3]]
        for d in candidates:
            env_file = d / ".env"
            if not env_file.is_file():
                continue
            for raw in env_file.read_text().splitlines():
                line = raw.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, val = line.partition("=")
                key = key.strip()
                val = val.strip().strip('"').strip("'")
                # Don't overwrite anything already in the real environment.
                os.environ.setdefault(key, val)
            if os.getenv("ANTHROPIC_API_KEY"):
                print(f"(loaded env from {env_file})")
                break
    if not os.getenv("ANTHROPIC_API_KEY"):
        print("Set ANTHROPIC_API_KEY in environment or .env before running.",
              file=sys.stderr)
        sys.exit(2)

    TRANSCRIPTS.mkdir(exist_ok=True)

    run([
        sys.executable, "mcp_client.py", "--suite",
        "--model", args.model,
        "--save-json", str(TRANSCRIPTS / "obj1_transcripts.json"),
        "--save-html", str(TRANSCRIPTS / "obj1_transcripts.html"),
    ], cwd=HERE / "objective1_mcp")

    run([
        sys.executable, "ingest.py",
        "--embeddings", args.embeddings, "--reset",
    ], cwd=HERE / "objective2_rag")

    run([
        sys.executable, "rag_assistant.py", "--suite",
        "--model", args.model,
        "--save-json", str(TRANSCRIPTS / "obj2_transcripts.json"),
        "--save-html", str(TRANSCRIPTS / "obj2_transcripts.html"),
    ], cwd=HERE / "objective2_rag")

    print("\nAll suites complete. Transcripts in", TRANSCRIPTS)


if __name__ == "__main__":
    main()
