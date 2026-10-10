from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import json
from .config import Settings
from .graph_store import GraphStore
from .pipeline import ingest
from .retrieval import search_entities, get_claim, neighborhood, baseline_paths

app = FastAPI(title="Cross-Paper GraphRAG prototype")


class TextInput(BaseModel):
    text: str
    title: str | None = None
    persist: bool = True


def store():
    s = Settings()
    return GraphStore(s.neo4j_uri, s.neo4j_username, s.neo4j_password, s.neo4j_database)


@app.get("/health")
def health():
    return {"status": "ok", "note": "Process health only; use /health/services for integrations"}


@app.get("/health/services")
def services():
    import httpx
    s = Settings()
    result = {"ollama": False, "neo4j": False}
    try:
        r = httpx.get(s.ollama_host.rstrip("/") + "/api/tags", timeout=3)
        result["ollama"] = r.is_success
    except httpx.HTTPError:
        pass
    try:
        db = store()
        try:
            db.verify()
            result["neo4j"] = True
        finally:
            db.close()
    except Exception:
        pass
    return result


@app.get("/runs/{run_id}")
def run_status(run_id: str):
    try:
        import uuid
        uuid.UUID(run_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid run ID") from exc
    path = Settings().run_dir / f"{run_id}.json"
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Run not found")
    return json.loads(path.read_text(encoding="utf-8"))


@app.post("/ingest/text")
def ingest_text(body: TextInput):
    try:
        output = ingest(Settings(), text=body.text, title=body.title, persist=body.persist)
        return {"run": output["run"], "paper": output["paper"], "claim_count": len(output["claims"]), "failed_chunks": len(output["chunk_errors"]), "persisted": output["persisted"]}
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get("/entities")
def entities(name: str, limit: int = 20):
    db = store()
    try:
        return search_entities(db, name, min(max(limit, 1), 100))
    finally:
        db.close()


@app.get("/claims/{claim_id}")
def claim(claim_id: str):
    db = store()
    try:
        result = get_claim(db, claim_id)
        if result is None:
            raise HTTPException(status_code=404, detail="Claim not found")
        return result
    finally:
        db.close()


@app.get("/entities/{entity_id}/neighbors")
def neighbors(entity_id: str, limit: int = 50):
    db = store()
    try:
        return neighborhood(db, entity_id, min(max(limit, 1), 100))
    finally:
        db.close()


@app.get("/paths/baseline")
def paths(source: str, target: str, max_hops: int = 3):
    db = store()
    try:
        return baseline_paths(db, source, target, max_hops)
    finally:
        db.close()
