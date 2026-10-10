import hashlib
import re
from .schemas import Chunk, Paper


def chunk_pages(paper: Paper, pages: list[tuple[int | None, str]], size: int, overlap: int) -> list[Chunk]:
    chunks = []
    for page, text in pages:
        if not text.strip():
            continue
        pos = 0
        while pos < len(text):
            end = min(pos + size, len(text))
            if end < len(text):
                boundaries = [m.end() for m in re.finditer(r"(?<=[.!?])\s+|\n\s*\n", text[pos:end])]
                if boundaries and boundaries[-1] >= size // 2:
                    end = pos + boundaries[-1]
            start = pos
            piece = text[start:end]
            if piece.strip():
                key = f"{paper.paper_id}:{page}:{start}:{end}".encode()
                chunks.append(Chunk(chunk_id="chunk:" + hashlib.sha256(key).hexdigest(), paper_id=paper.paper_id, text=piece, page=page, source_start=start, source_end=end))
            if end == len(text):
                break
            pos = max(pos + 1, end - overlap)
    return chunks


def split_chunk_for_retry(chunk: Chunk) -> tuple[Chunk, Chunk] | None:
    """Split a failed chunk once near its midpoint at a sentence boundary."""
    text = chunk.text
    boundaries = [m.end() for m in re.finditer(r"(?<=[.!?])\s+", text)]
    boundaries = [position for position in boundaries if text[:position].strip() and text[position:].strip()]
    if not boundaries:
        return None
    middle = min(boundaries, key=lambda position: abs(position - len(text) / 2))
    result = []
    for local_start, local_end in ((0, middle), (middle, len(text))):
        start = chunk.source_start + local_start
        end = chunk.source_start + local_end
        key = f"{chunk.paper_id}:{chunk.page}:{start}:{end}".encode()
        result.append(Chunk(chunk_id="chunk:" + hashlib.sha256(key).hexdigest(), paper_id=chunk.paper_id, text=text[local_start:local_end], page=chunk.page, section=chunk.section, source_start=start, source_end=end))
    return result[0], result[1]
