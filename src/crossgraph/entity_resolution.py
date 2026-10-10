import hashlib
import re
from .schemas import Mention, Entity


def normalize(name: str) -> str:
    return re.sub(r"\s+", " ", name.strip().casefold())


def resolve(mentions: list[Mention], paper_id: str, aliases: dict[tuple[str, str], str] | None = None) -> tuple[list[Entity], dict[str, str]]:
    aliases = aliases or {}
    entities: dict[str, Entity] = {}
    mapping = {}
    for m in mentions:
        norm = normalize(m.text)
        canonical = aliases.get((m.entity_type, norm))
        key = f"curated:{m.entity_type}:{normalize(canonical)}" if canonical else f"local:{paper_id}:{m.entity_type}:{norm}"
        eid = "entity:" + hashlib.sha256(key.encode()).hexdigest()
        if eid not in entities:
            entities[eid] = Entity(entity_id=eid, canonical_name=canonical or m.text, entity_type=m.entity_type, aliases=[m.text], resolution_method="curated_alias" if canonical else "paper_local_exact_name_type")
        elif m.text not in entities[eid].aliases:
            entities[eid].aliases.append(m.text)
        mapping[m.mention_id] = eid
    return list(entities.values()), mapping
