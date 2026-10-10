import hashlib
import re
from .schemas import Chunk, Mention, Claim, Extraction


class InvalidExtraction(ValueError):
    pass


def normalize_known_predicates(extraction: Extraction, allowed: list[str]) -> tuple[Extraction, list[str]]:
    """Map only unambiguous raw verb forms; keep an audit trail for review."""
    known = {
        "use": "USES",
        "uses": "USES",
        "outperform": "OUTPERFORMS",
        "outperforms": "OUTPERFORMS",
        "outperformed": "OUTPERFORMS",
        "outperformed by": "OUTPERFORMS",
        "is outperformed by": "OUTPERFORMS",
    }
    fixed = extraction.model_copy(deep=True)
    changes = []
    for i, claim in enumerate(fixed.claims):
        target = known.get(" ".join(claim.raw_predicate.casefold().split()))
        if claim.predicate is None and target in allowed:
            claim.predicate = target
            changes.append(f"claim[{i}] predicate normalized from raw_predicate to {target}")
    return fixed, changes


def repair_source_offsets(chunk: Chunk, extraction: Extraction) -> tuple[Extraction, list[str]]:
    """Repair only unique, nearby literal spans; never infer a missing entity."""
    fixed = extraction.model_copy(deep=True)
    repairs = []
    for i, mention in enumerate(fixed.mentions):
        if chunk.text[mention.start:mention.end] == mention.text:
            continue
        positions = [
            m.start()
            for m in re.finditer(re.escape(mention.text), chunk.text)
            if abs(m.start() - mention.start) <= 3
            and abs(m.end() - mention.end) <= 3
        ]
        if len(positions) == 1:
            mention.start = positions[0]
            mention.end = positions[0] + len(mention.text)
            repairs.append(f"mention[{i}] offset repaired")
    for i, claim in enumerate(fixed.claims):
        indices = [claim.subject_mention_index]
        if claim.object_mention_index is not None:
            indices.append(claim.object_mention_index)
        if any(index < 0 or index >= len(fixed.mentions) for index in indices):
            continue
        starts = [fixed.mentions[index].start for index in indices]
        ends = [fixed.mentions[index].end for index in indices]
        start = min(claim.evidence_start, *starts)
        end = max(claim.evidence_end, *ends)
        if 0 <= start < end <= len(chunk.text) and claim.evidence_start - start <= 3 and end - claim.evidence_end <= 3:
            if start != claim.evidence_start or end != claim.evidence_end:
                claim.evidence_start, claim.evidence_end = start, end
                repairs.append(f"claim[{i}] evidence offset repaired")
    return fixed, repairs


def validate(chunk: Chunk, extraction: Extraction, types: list[str], predicates: list[str]) -> tuple[list[Mention], list[Claim]]:
    mentions = []
    for item in extraction.mentions:
        if item.entity_type not in types or item.start < 0 or item.end <= item.start or chunk.text[item.start:item.end] != item.text:
            raise InvalidExtraction(f"Invalid mention span/type: {item.model_dump()}")
        mid = "mention:" + hashlib.sha256(f"{chunk.chunk_id}:{item.start}:{item.end}:{item.entity_type}".encode()).hexdigest()
        mentions.append(Mention(mention_id=mid, chunk_id=chunk.chunk_id, text=item.text, entity_type=item.entity_type, start=item.start, end=item.end, extractor="ollama"))
    claims = []
    seen = set()
    for item in extraction.claims:
        if item.subject_mention_index < 0 or item.subject_mention_index >= len(mentions) or (item.object_mention_index is not None and (item.object_mention_index < 0 or item.object_mention_index >= len(mentions))):
            raise InvalidExtraction("Claim refers to missing mention")
        if item.evidence_start < 0 or item.evidence_end <= item.evidence_start or item.evidence_end > len(chunk.text):
            raise InvalidExtraction("Invalid evidence offsets")
        subj = mentions[item.subject_mention_index]
        obj = mentions[item.object_mention_index] if item.object_mention_index is not None else None
        ev = chunk.text[item.evidence_start:item.evidence_end]
        if not (item.evidence_start <= subj.start and subj.end <= item.evidence_end) or (obj and not (item.evidence_start <= obj.start and obj.end <= item.evidence_end)):
            raise InvalidExtraction("Evidence does not contain claim entities")
        if obj is None and item.clause.grammatical_object and any(
            m.text.casefold() == item.clause.grammatical_object.casefold() for m in mentions
        ):
            raise InvalidExtraction("Claim omits an explicit object mention")
        raw = item.raw_predicate.casefold()
        if item.predicate is None and (re.search(r"\buses?\b", raw) or re.search(r"\boutperform(?:s|ed)?\b", raw)):
            raise InvalidExtraction("Claim omits normalized predicate for an explicit relation")
        if item.clause.voice == "PASSIVE" and item.clause.grammatical_subject:
            grammatical_subject = item.clause.grammatical_subject.strip().casefold()
            semantic_subject = subj.text.strip().casefold()
            if grammatical_subject == semantic_subject or semantic_subject.endswith(" " + grammatical_subject):
                raise InvalidExtraction("Passive claim uses grammatical subject as semantic subject")
            if obj is not None:
                matching_mentions = [
                    mention for mention in mentions
                    if mention.text.strip().casefold() == grammatical_subject
                    or mention.text.strip().casefold().endswith(" " + grammatical_subject)
                ]
                if matching_mentions and obj not in matching_mentions:
                    raise InvalidExtraction("Passive claim omits grammatical subject as semantic object")
        if item.predicate == "OUTPERFORMS" or re.search(r"\boutperform(?:s|ed)?\b", raw):
            for mention in mentions:
                if mention.entity_type == "Dataset" and re.search(r"\bon\s+" + re.escape(mention.text) + r"\b", ev, re.I):
                    if (item.qualifiers.get("dataset") or "").strip().casefold() != mention.text.casefold():
                        raise InvalidExtraction("Comparative claim omits dataset qualifier")
        reasons = []
        if item.predicate not in predicates:
            reasons.append("unknown_predicate")
        if item.clause.polarity == "UNKNOWN" or item.clause.voice == "UNKNOWN":
            reasons.append("unknown_clause_attributes")
        if item.clause.grammatical_subject and item.clause.grammatical_subject not in ev:
            reasons.append("grammatical_subject_not_in_evidence")
        if re.search(r"\b(?:not|never|no)\b", ev, re.I) and item.clause.polarity == "POSITIVE":
            reasons.append("possible_negation_mismatch")
        if item.clause.voice == "PASSIVE" and obj and item.clause.grammatical_subject == subj.text:
            reasons.append("possible_passive_direction_mismatch")
        signature = (subj.mention_id, obj.mention_id if obj else None, item.predicate, item.raw_predicate, item.clause.polarity, item.clause.modality, tuple(sorted(item.qualifiers.items())), ev)
        if signature in seen:
            continue
        seen.add(signature)
        # Absolute page offsets keep the same source claim stable across overlapping chunks.
        source_signature = (chunk.paper_id, chunk.page, chunk.source_start + item.evidence_start, chunk.source_start + item.evidence_end, subj.text, obj.text if obj else None, item.predicate, item.raw_predicate, item.clause.polarity, item.clause.modality, tuple(sorted(item.qualifiers.items())))
        cid = "claim:" + hashlib.sha256(repr(source_signature).encode()).hexdigest()
        claims.append(Claim(claim_id=cid, chunk_id=chunk.chunk_id, subject_mention_id=subj.mention_id, object_mention_id=obj.mention_id if obj else None, subject_entity_id="", object_entity_id=None, predicate=item.predicate if item.predicate in predicates else None, raw_predicate=item.raw_predicate, clause=item.clause, qualifiers=item.qualifiers, evidence_start=item.evidence_start, evidence_end=item.evidence_end, evidence_text=ev, status="needs_review" if reasons else "accepted", review_reasons=reasons))
    return mentions, claims
