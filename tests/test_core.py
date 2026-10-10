import pytest
from crossgraph.chunker import chunk_pages, split_chunk_for_retry
from crossgraph.document_parser import from_text
from crossgraph.ner import windows
from crossgraph.schemas import Clause, Extraction, ExtractionClaim, ExtractionMention
from crossgraph.validator import InvalidExtraction, validate, repair_source_offsets, normalize_known_predicates
from crossgraph.entity_resolution import resolve
from crossgraph.schemas import Mention
from crossgraph.schemas import Chunk
from crossgraph.config import Settings
from crossgraph.pipeline import ingest
from crossgraph.ollama_client import OllamaClient, OllamaExtractionError
import crossgraph.pipeline as pipeline


def make_chunk(text):
    paper, pages = from_text(text)
    return chunk_pages(paper, pages, 1600, 0)[0]


def test_windows_cover_long_text():
    text = "A long sentence. " * 200
    spans = list(windows(text, 80, 10))
    assert spans[0][0] == 0 and spans[-1][1] == len(text)
    assert all(b[0] <= a[1] for a, b in zip(spans, spans[1:]))


def test_failed_chunk_split_preserves_page_offsets():
    chunk = make_chunk("Method A uses Dataset D.\nMethod B is outperformed by Method A on Dataset D.")
    left, right = split_chunk_for_retry(chunk)
    assert left.text + right.text == chunk.text
    assert left.source_start == chunk.source_start
    assert left.source_end == right.source_start
    assert right.source_end == chunk.source_end
    assert right.text.startswith("Method B")


def test_passive_direction_preserved():
    text = "Method B is outperformed by Method A on Dataset D."
    chunk = make_chunk(text)
    extraction = Extraction(mentions=[
        ExtractionMention(text="Method B", entity_type="Method", start=0, end=8),
        ExtractionMention(text="Method A", entity_type="Method", start=28, end=36),
    ], claims=[ExtractionClaim(subject_mention_index=1, object_mention_index=0, predicate="OUTPERFORMS", raw_predicate="outperformed", clause=Clause(pattern="SVO", grammatical_subject="Method B", verb="outperformed", voice="PASSIVE", polarity="POSITIVE"), evidence_start=0, evidence_end=len(text), qualifiers={"dataset": "Dataset D"})])
    mentions, claims = validate(chunk, extraction, ["Method"], ["OUTPERFORMS"])
    assert claims[0].subject_mention_id == mentions[1].mention_id
    assert claims[0].object_mention_id == mentions[0].mention_id
    assert claims[0].status == "accepted"


def test_passive_comparison_requires_direction_object_and_dataset():
    text = "Method A uses Dataset D.\nMethod B is outperformed by Method A on Dataset D."
    chunk = make_chunk(text)
    mentions = [
        ExtractionMention(text="Method B", entity_type="Method", start=25, end=33),
        ExtractionMention(text="Method A", entity_type="Method", start=53, end=61),
        ExtractionMention(text="Dataset D", entity_type="Dataset", start=65, end=74),
    ]
    clause = Clause(pattern="SVO", grammatical_subject="Method B", grammatical_object="Method A", verb="outperformed", voice="PASSIVE", polarity="POSITIVE")

    def check(subject, obj, predicate, qualifiers):
        item = ExtractionClaim(subject_mention_index=subject, object_mention_index=obj, predicate=predicate, raw_predicate="outperformed", clause=clause, qualifiers=qualifiers, evidence_start=24, evidence_end=len(text))
        return validate(chunk, Extraction(mentions=mentions, claims=[item]), ["Method", "Dataset"], ["OUTPERFORMS"])

    with pytest.raises(InvalidExtraction, match="object mention"):
        check(0, None, None, {})
    with pytest.raises(InvalidExtraction, match="grammatical subject"):
        check(0, 1, "OUTPERFORMS", {"dataset": "Dataset D"})
    with pytest.raises(InvalidExtraction, match="semantic object"):
        check(1, 2, "OUTPERFORMS", {"dataset": "Dataset D"})
    with pytest.raises(InvalidExtraction, match="dataset qualifier"):
        check(1, 0, "OUTPERFORMS", {})
    _, claims = check(1, 0, "OUTPERFORMS", {"dataset": "Dataset D"})
    assert claims[0].status == "accepted"


def test_negation_mismatch_requires_review():
    text = "Method A does not improve Method B."
    chunk = make_chunk(text)
    extraction = Extraction(mentions=[ExtractionMention(text="Method A", entity_type="Method", start=0, end=8), ExtractionMention(text="Method B", entity_type="Method", start=26, end=34)], claims=[ExtractionClaim(subject_mention_index=0, object_mention_index=1, predicate="IMPROVES", raw_predicate="improve", clause=Clause(pattern="SVO", voice="ACTIVE", polarity="POSITIVE"), evidence_start=0, evidence_end=len(text))])
    _, claims = validate(chunk, extraction, ["Method"], ["IMPROVES"])
    assert claims[0].status == "needs_review"
    assert "possible_negation_mismatch" in claims[0].review_reasons


def test_invalid_offset_and_duplicate_claim():
    text = "Method A uses Dataset D."
    chunk = make_chunk(text)
    mentions = [ExtractionMention(text="Method A", entity_type="Method", start=0, end=8), ExtractionMention(text="Dataset D", entity_type="Dataset", start=14, end=23)]
    claim = ExtractionClaim(subject_mention_index=0, object_mention_index=1, predicate="USES", raw_predicate="uses", clause=Clause(pattern="SVO", voice="ACTIVE", polarity="POSITIVE"), evidence_start=0, evidence_end=len(text))
    _, claims = validate(chunk, Extraction(mentions=mentions, claims=[claim, claim]), ["Method", "Dataset"], ["USES"])
    assert len(claims) == 1
    with pytest.raises(InvalidExtraction):
        validate(chunk, Extraction(mentions=[ExtractionMention(text="wrong", entity_type="Method", start=0, end=8)]), ["Method"], ["USES"])


def test_cross_paper_link_requires_curated_alias():
    a = Mention(mention_id="a", chunk_id="a", text="Method A", entity_type="Method", start=0, end=8, extractor="test")
    b = Mention(mention_id="b", chunk_id="b", text="Method A", entity_type="Method", start=0, end=8, extractor="test")
    _, map_a = resolve([a], "paper-a")
    _, map_b = resolve([b], "paper-b")
    assert map_a["a"] != map_b["b"]
    aliases = {("Method", "method a"): "Method A"}
    _, map_a = resolve([a], "paper-a", aliases)
    _, map_b = resolve([b], "paper-b", aliases)
    assert map_a["a"] == map_b["b"]


def test_unique_nearby_offset_repair_and_ambiguous_span():
    chunk = make_chunk("Method A uses Dataset D.")
    raw = Extraction(mentions=[ExtractionMention(text="Dataset D", entity_type="Dataset", start=13, end=22)], claims=[])
    fixed, repairs = repair_source_offsets(chunk, raw)
    assert fixed.mentions[0].start == 14 and fixed.mentions[0].end == 23
    assert repairs and raw.mentions[0].start == 13
    distant_repeat = make_chunk("Method A uses Method A.")
    raw = Extraction(mentions=[ExtractionMention(text="Method A", entity_type="Method", start=1, end=9)])
    fixed, repairs = repair_source_offsets(distant_repeat, raw)
    assert repairs and fixed.mentions[0].start == 0
    ambiguous = make_chunk("A A")
    raw = Extraction(mentions=[ExtractionMention(text="A", entity_type="Method", start=1, end=2)])
    fixed, repairs = repair_source_offsets(ambiguous, raw)
    assert not repairs and fixed.mentions[0].start == 1


@pytest.mark.parametrize("failure", [InvalidExtraction, OllamaExtractionError])
def test_invalid_chunk_marks_run_partial_without_persisting(monkeypatch, tmp_path, failure):
    paper, _ = from_text("Bad. Method A uses Dataset D.")
    chunks = [
        Chunk(chunk_id="bad", paper_id=paper.paper_id, text="Bad.", source_start=0, source_end=4),
        Chunk(chunk_id="good", paper_id=paper.paper_id, text="Method A uses Dataset D.", source_start=5, source_end=29),
    ]
    monkeypatch.setattr(pipeline, "chunk_pages", lambda *args: chunks)

    def fake_extract(client, chunk, candidates, clauses, types, predicates, mode, audit):
        if chunk.chunk_id == "bad":
            raise failure("Invalid extraction")
        extraction = Extraction(
            mentions=[
                ExtractionMention(text="Method A", entity_type="Method", start=0, end=8),
                ExtractionMention(text="Dataset D", entity_type="Dataset", start=14, end=23),
            ],
            claims=[ExtractionClaim(subject_mention_index=0, object_mention_index=1, predicate="USES", raw_predicate="uses", clause=Clause(pattern="SVO", voice="ACTIVE", polarity="POSITIVE"), evidence_start=0, evidence_end=23)],
        )
        return validate(chunk, extraction, types, predicates)

    monkeypatch.setattr(pipeline, "extract_validated", fake_extract)
    settings = Settings(extraction_mode="text_only", enable_ner=False, enable_syntax=False, run_dir=tmp_path, neo4j_password="")
    result = ingest(settings, text="Bad. Method A uses Dataset D.", persist=True)
    assert result["run"].status == "partial"
    assert len(result["claims"]) == 1
    assert len(result["chunk_errors"]) == 1
    assert result["persisted"] is False
    assert (tmp_path / f"{result['run'].run_id}.json").is_file()


def test_failed_multisentence_chunk_retries_as_review_chunks(monkeypatch, tmp_path):
    text = "Method A uses Dataset D. Method B is outperformed by Method A on Dataset D."
    settings = Settings(extraction_mode="text_only", enable_ner=False, enable_syntax=False, run_dir=tmp_path)

    def fake_extract(client, chunk, candidates, clauses, types, predicates, mode, audit):
        if "uses" in chunk.text and "outperformed" in chunk.text:
            raise InvalidExtraction("mixed sentences")
        if "uses" in chunk.text:
            extraction = Extraction(mentions=[ExtractionMention(text="Method A", entity_type="Method", start=0, end=8), ExtractionMention(text="Dataset D", entity_type="Dataset", start=14, end=23)], claims=[ExtractionClaim(subject_mention_index=0, object_mention_index=1, predicate="USES", raw_predicate="uses", clause=Clause(pattern="SVO", voice="ACTIVE", polarity="POSITIVE"), evidence_start=0, evidence_end=23)])
            return validate(chunk, extraction, types, predicates)
        return [], []

    monkeypatch.setattr(pipeline, "extract_validated", fake_extract)
    result = ingest(settings, text=text, persist=False)
    assert result["run"].status == "completed"
    assert len(result["split_attempts"]) == 1
    assert len(result["chunks"]) == 2
    assert result["claims"][0].status == "needs_review"
    assert "adaptive_split" in result["claims"][0].review_reasons


def test_incomplete_ollama_json_reports_finish_reason(monkeypatch):
    calls = []

    class Response:
        def raise_for_status(self):
            pass

        def json(self):
            return {"message": {"content": '{"mentions": ['}, "done_reason": "length"}

    def fake_post(*args, **kwargs):
        calls.append(kwargs)
        return Response()

    monkeypatch.setattr("crossgraph.ollama_client.httpx.post", fake_post)
    with pytest.raises(OllamaExtractionError, match="done_reason='length'; content_chars=14"):
        OllamaClient("http://localhost:11434", "test-model", 1, 1024).extract("test")
    assert len(calls) == 2


def test_known_predicate_normalization_is_audited():
    raw = Extraction(claims=[ExtractionClaim(subject_mention_index=0, object_mention_index=1, predicate=None, raw_predicate="is outperformed by", clause=Clause(voice="PASSIVE"), evidence_start=0, evidence_end=10)])
    fixed, changes = normalize_known_predicates(raw, ["OUTPERFORMS"])
    assert fixed.claims[0].predicate == "OUTPERFORMS"
    assert raw.claims[0].predicate is None
    assert changes == ["claim[0] predicate normalized from raw_predicate to OUTPERFORMS"]
