import argparse
import json
from pathlib import Path
from .config import Settings
from .graph_store import GraphStore
from .pipeline import ingest


def main():
    parser = argparse.ArgumentParser(description="Cross-paper claim graph prototype")
    sub = parser.add_subparsers(dest="command", required=True)
    ingest_cmd = sub.add_parser("ingest")
    ingest_cmd.add_argument("path", type=Path)
    ingest_cmd.add_argument("--no-persist", action="store_true")
    claim_cmd = sub.add_parser("claim", help="Review a persisted claim")
    claim_actions = claim_cmd.add_subparsers(dest="claim_action", required=True)
    approve_cmd = claim_actions.add_parser("approve", help="Approve a claim and create its entity edge")
    approve_cmd.add_argument("claim_id")
    approve_cmd.add_argument("--reviewer", required=True)
    approve_cmd.add_argument("--note", required=True)
    args = parser.parse_args()
    if args.command == "ingest":
        if not args.path.is_file():
            parser.error(f"Input file not found: {args.path}. Provide an existing .txt or .pdf path.")
        result = ingest(Settings(), path=args.path, persist=not args.no_persist)
        print(json.dumps({"run_id": result["run"].run_id, "status": result["run"].status, "paper_id": result["paper"].paper_id, "claims": len(result["claims"]), "failed_chunks": len(result["chunk_errors"]), "persisted": result["persisted"]}, indent=2))
        if result["run"].status != "completed":
            parser.exit(2, f"Ingestion incomplete. Inspect data/runs/{result['run'].run_id}.json for chunk errors.\n")
    elif args.command == "claim" and args.claim_action == "approve":
        settings = Settings()
        graph = GraphStore(settings.neo4j_uri, settings.neo4j_username, settings.neo4j_password, settings.neo4j_database)
        try:
            result = graph.approve_claim(args.claim_id, args.reviewer, args.note)
        except (LookupError, ValueError) as exc:
            parser.exit(2, f"Approval failed: {exc}\n")
        finally:
            graph.close()
        print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
