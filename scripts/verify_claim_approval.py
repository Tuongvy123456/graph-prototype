"""Exercise manual approval and re-ingest in Neo4j, then roll back."""

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
    if {e.entity_id for e in entities} != {e["entity_id"] for e in saved["entities"]}:
        raise ValueError("Run used curated aliases; this check expects paper-local resolution")
    target = next((c for c in claims if c.object_entity_id and c.predicate), None)
    if target is None:
        raise ValueError("Run has no claim with an object and normalized predicate")

    settings = Settings()
    store = GraphStore(settings.neo4j_uri, settings.neo4j_username, settings.neo4j_password, settings.neo4j_database)
    query = (
        "MATCH (c:Claim {claim_id:$id}) "
        "OPTIONAL MATCH ()-[r:CLAIM_LINK {claim_id:$id}]->() "
        "RETURN c.status AS status, c.reviewed_by AS reviewed_by, "
        "c.review_reasons AS review_reasons, c.pre_review_reasons AS pre_review_reasons, "
        "collect(r {.*}) AS links"
    )
    try:
        store.verify()
        with store.driver.session(database=settings.neo4j_database) as session:
            before = session.run(query, id=target.claim_id).single()
            if before is None:
                raise ValueError("Claim is not persisted; ingest without --no-persist first")
            before = before.data()
            tx = session.begin_transaction()
            try:
                GraphStore._approve_claim(tx, target.claim_id, "transaction-test", "verified source text")
                approved = tx.run(query, id=target.claim_id).single().data()
                assert approved["status"] == "accepted" and len(approved["links"]) == 1
                assert approved["links"][0]["paper_id"] == paper.paper_id
                assert approved["links"][0]["chunk_id"] == target.chunk_id
                assert approved["links"][0]["evidence_text"] == target.evidence_text
                GraphStore._approve_claim(tx, target.claim_id, "second-reviewer", "repeat call")
                repeated = tx.run(query, id=target.claim_id).single().data()
                assert repeated["reviewed_by"] == "transaction-test"
                assert len(repeated["links"]) == 1
                GraphStore._write(tx, paper, chunks, mentions, entities, claims, mapping)
                reingested = tx.run(query, id=target.claim_id).single().data()
                assert reingested["status"] == "accepted" and len(reingested["links"]) == 1
                assert reingested["reviewed_by"] == "transaction-test"
            finally:
                tx.rollback()
            after = session.run(query, id=target.claim_id).single().data()
            assert before == after, (before, after)
            print(json.dumps({"transaction": "rolled_back", "claim_id": target.claim_id, "approval": "passed", "reingest_preserved_approval": True}))
    finally:
        store.close()


if __name__ == "__main__":
    main()
