import json
from .schemas import Chunk, Mention, Clause, Extraction
from .validator import InvalidExtraction, validate, repair_source_offsets, normalize_known_predicates

PROMPT_VERSION = "claim-v2"


def make_prompt(chunk: Chunk, mentions: list[Mention], clauses: list[Clause], entity_types: list[str], predicates: list[str], mode: str) -> str:
    hints = {"candidate_mentions": [m.model_dump(exclude={"mention_id", "chunk_id"}) for m in mentions], "syntax_hints": [c.model_dump() for c in clauses] if mode == "syntax_assisted" else []}
    return f"""Extract only claims explicitly supported by the SOURCE TEXT. Return JSON matching the supplied schema. All character offsets are zero-based, end-exclusive offsets into SOURCE TEXT. Copy entity spans exactly. CRITICAL: populate the top-level mentions array for every subject and object before writing claims. subject_mention_index and object_mention_index are zero-based positions in that array; never return a claim with an empty mentions array or an out-of-range index. If an entity name occurs twice, create separate mentions with the offsets of each occurrence; a claim must reference occurrences inside its evidence span. Semantic subject/object must follow the relation meaning, including passive clauses: 'Method B is outperformed by Method A on Dataset D' means subject Method A, predicate OUTPERFORMS, object Method B, qualifier dataset Dataset D, voice PASSIVE. Do not drop the object or normalized predicate to work around an offset error. Preserve negation, modality and conditions. Unknown predicate: null, keep raw_predicate. No invented entities, evidence or metrics. Omit unresolved claims. An SV event can have null object only when no explicit object appears in the source clause. Candidate types: {entity_types}. Allowed normalized predicates: {predicates}. Clause hints are suggestions, not ground truth.\nMODE: {mode}\nHINTS: {json.dumps(hints, ensure_ascii=False)}\nSOURCE TEXT:\n{chunk.text}"""


def extract(client, chunk: Chunk, mentions: list[Mention], clauses: list[Clause], entity_types: list[str], predicates: list[str], mode: str) -> Extraction:
    return client.extract(make_prompt(chunk, mentions, clauses, entity_types, predicates, mode))


def extract_validated(client, chunk: Chunk, mentions: list[Mention], clauses: list[Clause], entity_types: list[str], predicates: list[str], mode: str, audit: list[dict] | None = None):
    prompt = make_prompt(chunk, mentions, clauses, entity_types, predicates, mode)
    for attempt in range(1, 4):
        output = client.extract(prompt)
        repaired, repairs = repair_source_offsets(chunk, output)
        repaired, predicate_repairs = normalize_known_predicates(repaired, predicates)
        try:
            validated_mentions, claims = validate(chunk, repaired, entity_types, predicates)
            if repairs:
                for claim in claims:
                    claim.status = "needs_review"
                    claim.review_reasons.append("source_offset_repaired")
            if predicate_repairs:
                for claim in claims:
                    claim.status = "needs_review"
                    claim.review_reasons.append("predicate_normalized_from_raw")
            if audit is not None:
                audit.append({"chunk_id": chunk.chunk_id, "attempt": attempt, "extraction": output.model_dump(), "offset_repairs": repairs, "predicate_repairs": predicate_repairs, "validation_error": None})
            return validated_mentions, claims
        except InvalidExtraction as exc:
            if audit is not None:
                audit.append({"chunk_id": chunk.chunk_id, "attempt": attempt, "extraction": output.model_dump(), "offset_repairs": repairs, "predicate_repairs": predicate_repairs, "validation_error": str(exc)})
            if attempt == 3:
                raise
            prompt += f"\nYour previous JSON failed validation: {exc}. Regenerate the full JSON. Recompute all start/end offsets from SOURCE TEXT, counting spaces and punctuation; end is exclusive. Include every subject/object in mentions before referencing its zero-based index."
