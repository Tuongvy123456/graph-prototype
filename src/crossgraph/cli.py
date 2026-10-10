import argparse
import json
from pathlib import Path
from .config import Settings
from .pipeline import ingest


def main():
    parser = argparse.ArgumentParser(description="Cross-paper claim graph prototype")
    sub = parser.add_subparsers(dest="command", required=True)
    ingest_cmd = sub.add_parser("ingest")
    ingest_cmd.add_argument("path", type=Path)
    ingest_cmd.add_argument("--no-persist", action="store_true")
    args = parser.parse_args()
    if args.command == "ingest":
        if not args.path.is_file():
            parser.error(f"Input file not found: {args.path}. Provide an existing .txt or .pdf path.")
        result = ingest(Settings(), path=args.path, persist=not args.no_persist)
        print(json.dumps({"run_id": result["run"].run_id, "status": result["run"].status, "paper_id": result["paper"].paper_id, "claims": len(result["claims"]), "failed_chunks": len(result["chunk_errors"]), "persisted": result["persisted"]}, indent=2))
        if result["run"].status != "completed":
            parser.exit(2, f"Ingestion incomplete. Inspect data/runs/{result['run'].run_id}.json for chunk errors.\n")


if __name__ == "__main__":
    main()
