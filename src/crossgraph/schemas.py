from typing import Literal
from pydantic import BaseModel, Field


class Paper(BaseModel):
    paper_id: str
    title: str | None = None
    source_path: str | None = None
    source_hash: str
    metadata: dict[str, str] = Field(default_factory=dict)


class Chunk(BaseModel):
    chunk_id: str
    paper_id: str
    text: str
    page: int | None = None
    section: str | None = None
    source_start: int
    source_end: int


class Mention(BaseModel):
    mention_id: str
    chunk_id: str
    text: str
    entity_type: str
    start: int
    end: int
    extractor: str
    score: float | None = None


class Clause(BaseModel):
    pattern: Literal["SVO", "SVC", "SV", "OTHER", "UNKNOWN"] = "UNKNOWN"
    grammatical_subject: str | None = None
    verb: str | None = None
    grammatical_object: str | None = None
    voice: Literal["ACTIVE", "PASSIVE", "UNKNOWN"] = "UNKNOWN"
    polarity: Literal["POSITIVE", "NEGATIVE", "UNKNOWN"] = "UNKNOWN"
    modality: str | None = None
    start: int | None = None
    end: int | None = None


class ExtractionMention(BaseModel):
    text: str
    entity_type: str
    start: int
    end: int


class ExtractionClaim(BaseModel):
    subject_mention_index: int
    object_mention_index: int | None = None
    predicate: str | None = None
    raw_predicate: str
    clause: Clause
    qualifiers: dict[str, str | None] = Field(default_factory=dict)
    evidence_start: int
    evidence_end: int


class Extraction(BaseModel):
    mentions: list[ExtractionMention] = Field(default_factory=list)
    claims: list[ExtractionClaim] = Field(default_factory=list)


class Entity(BaseModel):
    entity_id: str
    canonical_name: str
    entity_type: str
    aliases: list[str] = Field(default_factory=list)
    resolution_method: str = "exact_name_type"


class Claim(BaseModel):
    claim_id: str
    chunk_id: str
    subject_mention_id: str
    object_mention_id: str | None = None
    subject_entity_id: str
    object_entity_id: str | None = None
    predicate: str | None = None
    raw_predicate: str
    clause: Clause
    qualifiers: dict[str, str | None]
    evidence_start: int
    evidence_end: int
    evidence_text: str
    status: Literal["accepted", "needs_review", "rejected"]
    review_reasons: list[str] = Field(default_factory=list)


class RunRecord(BaseModel):
    run_id: str
    paper_id: str
    mode: str
    settings: dict[str, str | int | bool]
    started_at: str
    finished_at: str | None = None
    status: str = "running"
    errors: list[str] = Field(default_factory=list)
    chunks: int = 0
    claims: int = 0
