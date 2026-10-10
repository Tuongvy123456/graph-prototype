"""Verify Neo4j write/idempotency using a saved run, then roll back every write."""

import argparse
import json
from pathlib import Path

from crossgraph.config import Settings
from crossgraph.entity_resolution import resolve
from crossgraph.graph_store import GraphStore
from crossgraph.schemas import Chunk, Claim, Mention, Paper


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("run_json", type=Path)
    args = parser.parse_args()
    saved = json.loads(args.run_json.read_text(encoding="utf-8"))
    paper = Paper.model_validate(saved["paper"])
    chunks = [Chunk.model_validate(item) for item in saved["chunks"]]
    mentions = [Mention.model_validate(item) for item in saved["mentions"]]
    claims = [Claim.model_validate(item) for item in saved["claims"]]
    entities, mapping = resolve(mentions, paper.paper_id)
    if {item.entity_id for item in entities} != {item["entity_id"] for item in saved["entities"]}:
        raise ValueError("Run used curated aliases; this smoke script expects paper-local resolution")
    if not claims:
        raise ValueError("Run has no claims to verify")

    settings = Settings()
    store = GraphStore(settings.neo4j_uri, settings.neo4j_username, settings.neo4j_password, settings.neo4j_database)
    try:
        store.verify()
        with store.driver.session(database=settings.neo4j_database) as session:
            before = [session.run("MATCH (c:Claim {claim_id:$id}) RETURN count(c) AS n", id=claim.claim_id).single()["n"] for claim in claims]
            tx = session.begin_transaction()
            try:
                def counts():
                    return [
                        {
                            "claim_nodes": tx.run("MATCH (c:Claim {claim_id:$id}) RETURN count(c) AS n", id=claim.claim_id).single()["n"],
                            "subject_edges": tx.run("MATCH (c:Claim {claim_id:$id})-[:SUBJECT]->() RETURN count(*) AS n", id=claim.claim_id).single()["n"],
                            "evidence_edges": tx.run("MATCH (c:Claim {claim_id:$id})-[:SUPPORTED_BY]->() RETURN count(*) AS n", id=claim.claim_id).single()["n"],
                            "projection_edges": tx.run("MATCH ()-[r:CLAIM_LINK {claim_id:$id}]->() RETURN count(r) AS n", id=claim.claim_id).single()["n"],
                        }
                        for claim in claims
                    ]

                store._write(tx, paper, chunks, mentions, entities, claims, mapping)
                first = counts()
                store._write(tx, paper, chunks, mentions, entities, claims, mapping)
                second = counts()
                assert first == second, (first, second)
                assert all(row["claim_nodes"] == 1 and row["subject_edges"] == 1 and row["evidence_edges"] == 1 for row in second)
            finally:
                tx.rollback()
            after = [session.run("MATCH (c:Claim {claim_id:$id}) RETURN count(c) AS n", id=claim.claim_id).single()["n"] for claim in claims]
            assert before == after, (before, after)
            print(json.dumps({"transaction": "rolled_back", "claims_checked": len(claims), "idempotent": True, "counts": second}))
    finally:
        store.close()


if __name__ == "__main__":
    main()
