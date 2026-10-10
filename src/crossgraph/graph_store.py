import json
from neo4j import GraphDatabase
from .schemas import Paper, Chunk, Mention, Entity, Claim


CONSTRAINTS = [
    "CREATE CONSTRAINT paper_id IF NOT EXISTS FOR (n:Paper) REQUIRE n.paper_id IS UNIQUE",
    "CREATE CONSTRAINT chunk_id IF NOT EXISTS FOR (n:Chunk) REQUIRE n.chunk_id IS UNIQUE",
    "CREATE CONSTRAINT mention_id IF NOT EXISTS FOR (n:Mention) REQUIRE n.mention_id IS UNIQUE",
    "CREATE CONSTRAINT entity_id IF NOT EXISTS FOR (n:Entity) REQUIRE n.entity_id IS UNIQUE",
    "CREATE CONSTRAINT claim_id IF NOT EXISTS FOR (n:Claim) REQUIRE n.claim_id IS UNIQUE",
]


class GraphStore:
    def __init__(self, uri: str, username: str, password: str, database: str = "neo4j"):
        if not password:
            raise ValueError("NEO4J_PASSWORD is required for graph persistence")
        self.driver = GraphDatabase.driver(uri, auth=(username, password))
        self.database = database

    def close(self):
        self.driver.close()

    def verify(self):
        self.driver.verify_connectivity()

    def setup(self):
        with self.driver.session(database=self.database) as session:
            for query in CONSTRAINTS:
                session.run(query).consume()

    def save(self, paper: Paper, chunks: list[Chunk], mentions: list[Mention], entities: list[Entity], claims: list[Claim], mapping: dict[str, str]):
        with self.driver.session(database=self.database) as session:
            session.execute_write(self._write, paper, chunks, mentions, entities, claims, mapping)

    @staticmethod
    def _write(tx, paper, chunks, mentions, entities, claims, mapping):
        tx.run("MERGE (p:Paper {paper_id:$id}) SET p.title=$title, p.source_path=$path, p.source_hash=$hash, p.metadata_json=$metadata", id=paper.paper_id, title=paper.title, path=paper.source_path, hash=paper.source_hash, metadata=json.dumps(paper.metadata)).consume()
        for c in chunks:
            tx.run("MATCH (p:Paper {paper_id:$paper_id}) MERGE (c:Chunk {chunk_id:$id}) SET c.text=$text, c.page=$page, c.section=$section, c.source_start=$start, c.source_end=$end MERGE (p)-[:HAS_CHUNK]->(c)", paper_id=paper.paper_id, id=c.chunk_id, text=c.text, page=c.page, section=c.section, start=c.source_start, end=c.source_end).consume()
        for e in entities:
            tx.run("MERGE (e:Entity {entity_id:$id}) SET e.canonical_name=$name, e.entity_type=$type, e.aliases=coalesce(e.aliases, []) + [a IN $aliases WHERE NOT a IN coalesce(e.aliases, [])], e.resolution_method=$method", id=e.entity_id, name=e.canonical_name, type=e.entity_type, aliases=e.aliases, method=e.resolution_method).consume()
        for m in mentions:
            tx.run("MATCH (c:Chunk {chunk_id:$chunk_id}), (e:Entity {entity_id:$entity_id}) MERGE (m:Mention {mention_id:$id}) SET m.text=$text, m.entity_type=$type, m.start=$start, m.end=$end, m.extractor=$extractor, m.score=$score MERGE (m)-[:IN_CHUNK]->(c) MERGE (m)-[:REFERS_TO]->(e)", chunk_id=m.chunk_id, entity_id=mapping[m.mention_id], id=m.mention_id, text=m.text, type=m.entity_type, start=m.start, end=m.end, extractor=m.extractor, score=m.score).consume()
        for c in claims:
            tx.run("MATCH ()-[r:CLAIM_LINK {claim_id:$id}]->() DELETE r", id=c.claim_id).consume()
            tx.run("MATCH (c:Claim {claim_id:$id})-[r]->() WHERE type(r) IN ['SUBJECT', 'OBJECT', 'SUPPORTED_BY'] DELETE r", id=c.claim_id).consume()
            tx.run("MATCH (ch:Chunk {chunk_id:$chunk_id}), (s:Entity {entity_id:$subject_id}) MERGE (c:Claim {claim_id:$id}) SET c.predicate=$predicate, c.raw_predicate=$raw, c.clause_json=$clause, c.qualifiers_json=$qualifiers, c.evidence_start=$start, c.evidence_end=$end, c.evidence_text=$text, c.status=$status, c.review_reasons=$reasons MERGE (c)-[:SUBJECT]->(s) MERGE (c)-[:SUPPORTED_BY]->(ch)", chunk_id=c.chunk_id, subject_id=c.subject_entity_id, id=c.claim_id, predicate=c.predicate, raw=c.raw_predicate, clause=c.clause.model_dump_json(), qualifiers=json.dumps(c.qualifiers), start=c.evidence_start, end=c.evidence_end, text=c.evidence_text, status=c.status, reasons=c.review_reasons).consume()
            if c.object_entity_id:
                tx.run("MATCH (c:Claim {claim_id:$id}), (o:Entity {entity_id:$object_id}) MERGE (c)-[:OBJECT]->(o)", id=c.claim_id, object_id=c.object_entity_id).consume()
            if c.status == "accepted" and c.object_entity_id:
                tx.run("MATCH (s:Entity {entity_id:$subject_id}), (o:Entity {entity_id:$object_id}) MERGE (s)-[r:CLAIM_LINK {claim_id:$claim_id}]->(o) SET r.predicate=$predicate", subject_id=c.subject_entity_id, object_id=c.object_entity_id, claim_id=c.claim_id, predicate=c.predicate).consume()

    def query(self, cypher: str, **params):
        with self.driver.session(database=self.database) as session:
            return [r.data() for r in session.run(cypher, **params)]
