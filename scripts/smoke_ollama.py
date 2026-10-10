"""Manual live Ollama check with a synthetic input sentence; no graph write."""

import argparse
import json
import os
from crossgraph.chunker import chunk_pages
from crossgraph.document_parser import from_text
from crossgraph.extractor import extract_validated
from crossgraph.ollama_client import OllamaClient


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--text", default="Method A uses Dataset D.")
    args = parser.parse_args()
    paper, pages = from_text(args.text, "synthetic-smoke-input")
    chunk = chunk_pages(paper, pages, 1600, 0)[0]
    types = ["Method", "Dataset", "Concept", "Task", "Metric"]
    predicates = ["USES", "EVALUATED_ON", "OUTPERFORMS", "IMPROVES", "COMPARES_WITH", "ADDRESSES", "MEASURES", "PRODUCES", "IS_A"]
    client = OllamaClient(os.getenv("OLLAMA_HOST", "http://localhost:11434"), os.getenv("OLLAMA_MODEL", "qwen3.5:9b"), 120, 8192, False)
    audit = []
    try:
        mentions, claims = extract_validated(client, chunk, [], [], types, predicates, "text_only", audit)
        print(json.dumps({"input_kind": "synthetic", "model": client.model, "attempts": audit, "validated_mentions": [m.model_dump() for m in mentions], "validated_claims": [c.model_dump() for c in claims]}, indent=2, ensure_ascii=False))
    except Exception:
        print(json.dumps({"input_kind": "synthetic", "model": client.model, "attempts": audit}, indent=2, ensure_ascii=False))
        raise


if __name__ == "__main__":
    main()
