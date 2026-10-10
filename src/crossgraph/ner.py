import hashlib
import re
from .schemas import Chunk, Mention

LABELS = {
    "scientific method": "Method",
    "dataset": "Dataset",
    "scientific concept": "Concept",
    "research task": "Task",
    "evaluation metric": "Metric",
}


class NER:
    def __init__(self, model_name: str, device: str = "cpu"):
        from gliner import GLiNER
        self.model = GLiNER.from_pretrained(model_name)
        self.model.to(device)

    def extract(self, chunk: Chunk, max_chars: int = 900) -> list[Mention]:
        found: dict[tuple[int, int, str], Mention] = {}
        for window_start, window_end in windows(chunk.text, max_chars, 100):
            window = chunk.text[window_start:window_end]
            for item in self.model.predict_entities(window, list(LABELS), threshold=0.4):
                start, end = window_start + item["start"], window_start + item["end"]
                label = LABELS[item["label"]]
                key = (start, end, label)
                mid = hashlib.sha256(f"{chunk.chunk_id}:{start}:{end}:{label}".encode()).hexdigest()
                found[key] = Mention(mention_id="mention:" + mid, chunk_id=chunk.chunk_id, text=chunk.text[start:end], entity_type=label, start=start, end=end, extractor="gliner", score=item.get("score"))
        return list(found.values())


def windows(text: str, size: int, overlap: int):
    if overlap >= size:
        raise ValueError("overlap must be smaller than size")
    pos = 0
    while pos < len(text):
        end = min(pos + size, len(text))
        if end < len(text):
            matches = list(re.finditer(r"\s+", text[pos + size // 2:end]))
            if matches:
                end = pos + size // 2 + matches[-1].end()
        yield pos, end
        if end == len(text):
            break
        pos = end - overlap
