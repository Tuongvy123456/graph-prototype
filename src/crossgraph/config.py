from pathlib import Path
from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    ollama_host: str = "http://localhost:11434"
    ollama_model: str = "qwen3.5:9b"
    ollama_embed_model: str = "qwen3-embedding:0.6b"
    gliner_model: str = "urchade/gliner_medium-v2.1"
    spacy_model: str = "en_core_web_trf"
    ner_device: str = "cpu"
    syntax_device: str = "cpu"
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_username: str = "neo4j"
    neo4j_password: str = ""
    neo4j_database: str = "neo4j"
    extraction_mode: str = "syntax_assisted"
    enable_ner: bool = True
    enable_syntax: bool = True
    chunk_size: int = Field(default=1600, ge=300)
    chunk_overlap: int = Field(default=150, ge=0)
    ollama_num_ctx: int = 8192
    ollama_think: bool = False
    request_timeout: float = 120
    run_dir: Path = Path("data/runs")
    entity_aliases_file: Path | None = None
    entity_types: list[str] = ["Method", "Dataset", "Concept", "Task", "Metric"]
    predicates: list[str] = ["USES", "EVALUATED_ON", "OUTPERFORMS", "IMPROVES", "COMPARES_WITH", "ADDRESSES", "MEASURES", "PRODUCES", "IS_A"]

    @model_validator(mode="after")
    def check(self):
        if self.extraction_mode not in {"syntax_assisted", "text_only"}:
            raise ValueError("EXTRACTION_MODE must be syntax_assisted or text_only")
        if self.chunk_overlap >= self.chunk_size:
            raise ValueError("CHUNK_OVERLAP must be smaller than CHUNK_SIZE")
        return self
