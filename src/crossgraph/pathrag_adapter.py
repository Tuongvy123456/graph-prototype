from typing import Protocol


class PathRAGAdapter(Protocol):
    """Contract for a future adapter to a verified PathRAG source/version."""

    def index_claim_graph(self, graph_store) -> None: ...
    def retrieve(self, query: str, limit: int = 10) -> list[dict]: ...


def pathrag_available() -> bool:
    return False
