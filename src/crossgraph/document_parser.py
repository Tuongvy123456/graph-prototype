import hashlib
from pathlib import Path
from .schemas import Paper


def read_document(path: Path) -> tuple[Paper, list[tuple[int | None, str]]]:
    path = path.resolve()
    content = path.read_bytes()
    digest = hashlib.sha256(content).hexdigest()
    paper = Paper(paper_id=f"paper:{digest}", source_path=str(path), source_hash=digest, title=path.stem)
    if path.suffix.lower() == ".txt":
        pages = [(None, content.decode("utf-8-sig"))]
    elif path.suffix.lower() == ".pdf":
        import pymupdf
        with pymupdf.open(stream=content, filetype="pdf") as doc:
            pages = [(i + 1, page.get_text(sort=True)) for i, page in enumerate(doc)]
        if not any(text.strip() for _, text in pages):
            raise ValueError("PDF has no extractable text; OCR is required")
    else:
        raise ValueError("Only .txt and .pdf are supported")
    return paper, pages


def from_text(text: str, title: str | None = None) -> tuple[Paper, list[tuple[None, str]]]:
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return Paper(paper_id=f"paper:{digest}", title=title, source_hash=digest), [(None, text)]
