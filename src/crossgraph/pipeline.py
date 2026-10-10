import json
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from .chunker import chunk_pages, split_chunk_for_retry
from .config import Settings
from .document_parser import from_text, read_document
from .entity_resolution import resolve, normalize
from .extractor import extract_validated, PROMPT_VERSION
from .graph_store import GraphStore
from .ner import NER
from .ollama_client import OllamaClient, OllamaExtractionError
from .schemas import RunRecord
from .syntax import Syntax
from .validator import InvalidExtraction


def ingest(settings: Settings, path: Path | None = None, text: str | None = None, title: str | None = None, persist: bool = True) -> dict:
    if (path is None) == (text is None):
        raise ValueError("Provide exactly one of path or text")
    paper, pages = read_document(path) if path else from_text(text, title)
    initial_chunks = chunk_pages(paper, pages, settings.chunk_size, settings.chunk_overlap)
    if not initial_chunks:
        raise ValueError("Document contains no extractable text")
    run = RunRecord(run_id=str(uuid.uuid4()), paper_id=paper.paper_id, mode=settings.extraction_mode, started_at=datetime.now(timezone.utc).isoformat(), settings={"ollama_model": settings.ollama_model, "ollama_think": settings.ollama_think, "gliner_model": settings.gliner_model, "spacy_model": settings.spacy_model, "enable_ner": settings.enable_ner, "enable_syntax": settings.enable_syntax, "prompt_version": PROMPT_VERSION, "chunk_size": settings.chunk_size, "chunk_overlap": settings.chunk_overlap})
    output = {"run": run, "paper": paper, "chunks": [], "source_chunk_count": len(initial_chunks), "mentions": [], "entities": [], "claims": [], "extraction_attempts": [], "split_attempts": [], "chunk_errors": [], "persisted": False}
    start = time.monotonic()
    try:
        ner = NER(settings.gliner_model, settings.ner_device) if settings.enable_ner and settings.extraction_mode == "syntax_assisted" else None
        syntax = Syntax(settings.spacy_model, settings.syntax_device) if settings.enable_syntax and settings.extraction_mode == "syntax_assisted" else None
        client = OllamaClient(settings.ollama_host, settings.ollama_model, settings.request_timeout, settings.ollama_num_ctx, settings.ollama_think)
        pending = [(chunk, 0) for chunk in initial_chunks]
        while pending:
            chunk, split_depth = pending.pop(0)
            candidates = ner.extract(chunk) if ner else []
            clauses = syntax.analyze(chunk) if syntax else []
            try:
                mentions, claims = extract_validated(client, chunk, candidates, clauses, settings.entity_types, settings.predicates, settings.extraction_mode, output["extraction_attempts"])
            except (InvalidExtraction, OllamaExtractionError) as exc:
                parts = split_chunk_for_retry(chunk) if split_depth == 0 else None
                if parts:
                    output["split_attempts"].append({"chunk_id": chunk.chunk_id, "page": chunk.page, "reason": f"{type(exc).__name__}: {exc}", "child_chunk_ids": [part.chunk_id for part in parts]})
                    pending[0:0] = [(part, split_depth + 1) for part in parts]
                    continue
                output["chunk_errors"].append({"chunk_id": chunk.chunk_id, "page": chunk.page, "source_start": chunk.source_start, "source_end": chunk.source_end, "error": f"{type(exc).__name__}: {exc}"})
                output["chunks"].append(chunk)
                continue
            if split_depth:
                for claim in claims:
                    claim.status = "needs_review"
                    if "adaptive_split" not in claim.review_reasons:
                        claim.review_reasons.append("adaptive_split")
            output["chunks"].append(chunk)
            output["mentions"].extend(mentions)
            output["claims"].extend(claims)
        unique_claims = {}
        for claim in output["claims"]:
            unique_claims.setdefault(claim.claim_id, claim)
        output["claims"] = list(unique_claims.values())
        aliases = {}
        if settings.entity_aliases_file:
            raw_aliases = json.loads(settings.entity_aliases_file.read_text(encoding="utf-8"))
            aliases = {(record["entity_type"], normalize(record["name"])): record["canonical_name"] for record in raw_aliases}
        entities, mapping = resolve(output["mentions"], paper.paper_id, aliases)
        output["entities"] = entities
        for claim in output["claims"]:
            claim.subject_entity_id = mapping[claim.subject_mention_id]
            claim.object_entity_id = mapping[claim.object_mention_id] if claim.object_mention_id else None
        if persist and not output["chunk_errors"]:
            store = GraphStore(settings.neo4j_uri, settings.neo4j_username, settings.neo4j_password, settings.neo4j_database)
            try:
                store.verify()
                store.setup()
                store.save(paper, output["chunks"], output["mentions"], entities, output["claims"], mapping)
                output["persisted"] = True
            finally:
                store.close()
        if output["chunk_errors"]:
            run.status = "partial" if output["claims"] else "failed"
            run.errors.append(f"{len(output['chunk_errors'])} of {len(output['chunks'])} final chunks failed extraction or validation; graph persistence skipped")
        else:
            run.status = "completed"
    except Exception as exc:
        run.status = "failed"
        run.errors.append(f"{type(exc).__name__}: {exc}")
        raise
    finally:
        run.finished_at = datetime.now(timezone.utc).isoformat()
        run.chunks = len(output["chunks"])
        run.claims = len(output["claims"])
        output["latency_seconds"] = round(time.monotonic() - start, 3)
        settings.run_dir.mkdir(parents=True, exist_ok=True)
        (settings.run_dir / f"{run.run_id}.json").write_text(json.dumps(output, default=lambda x: x.model_dump() if hasattr(x, "model_dump") else str(x), ensure_ascii=False, indent=2), encoding="utf-8")
    return output
