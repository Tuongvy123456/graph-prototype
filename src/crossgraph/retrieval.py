from .graph_store import GraphStore


def search_entities(store: GraphStore, name: str, limit: int = 20):
    return store.query("MATCH (e:Entity) WHERE toLower(e.canonical_name) CONTAINS toLower($name) OR any(a IN e.aliases WHERE toLower(a) CONTAINS toLower($name)) RETURN e.entity_id AS entity_id, e.canonical_name AS name, e.entity_type AS type, e.aliases AS aliases LIMIT $limit", name=name, limit=limit)


def get_claim(store: GraphStore, claim_id: str):
    rows = store.query("MATCH (c:Claim {claim_id:$claim_id})-[:SUBJECT]->(s:Entity) MATCH (c)-[:SUPPORTED_BY]->(ch:Chunk)<-[:HAS_CHUNK]-(p:Paper) OPTIONAL MATCH (c)-[:OBJECT]->(o:Entity) RETURN c {.*} AS claim, s {.*} AS subject, o {.*} AS object, ch.chunk_id AS chunk_id, ch.page AS page, p.paper_id AS paper_id, p.title AS paper_title, p.source_path AS source_path", claim_id=claim_id)
    return rows[0] if rows else None


def neighborhood(store: GraphStore, entity_id: str, limit: int = 50):
    return store.query("MATCH (e:Entity {entity_id:$id})-[r:CLAIM_LINK]-(other:Entity) MATCH (c:Claim {claim_id:r.claim_id}) RETURN other.entity_id AS entity_id, other.canonical_name AS name, r.claim_id AS claim_id, c.predicate AS predicate, c.qualifiers_json AS qualifiers_json, c.evidence_text AS evidence LIMIT $limit", id=entity_id, limit=limit)


def baseline_paths(store: GraphStore, source_id: str, target_id: str, max_hops: int = 3, limit: int = 10):
    if max_hops not in {1, 2, 3}:
        raise ValueError("max_hops must be 1, 2, or 3")
    # The hop bound is validated before interpolation; identifiers remain parameters.
    query = f"MATCH p=(a:Entity {{entity_id:$source}})-[:CLAIM_LINK*1..{max_hops}]-(b:Entity {{entity_id:$target}}) RETURN [n IN nodes(p) | n.entity_id] AS entity_ids, [r IN relationships(p) | r.claim_id] AS claim_ids LIMIT $limit"
    paths = store.query(query, source=source_id, target=target_id, limit=limit)
    for path in paths:
        path["claims"] = [get_claim(store, cid) for cid in path["claim_ids"]]
    return paths
