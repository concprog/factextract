from pathlib import Path
from functools import lru_cache
from pydantic import BaseModel, field_validator


class IngestConfig(BaseModel):
    header: bool = False
    footer: bool = False
    table_strategy: str = "lines_strict"
    tokenizer: str = "gpt2"
    chunk_size: int = 2048
    chunk_overlap: int = 128
    min_sentences_per_chunk: int = 1


class Config(BaseModel):
    graph_db_path: Path
    metadata_db_path: Path
    llm_model: str = "gemini/gemini-3.5-flash-lite"
    ingest: IngestConfig = IngestConfig()

    @field_validator("graph_db_path", "metadata_db_path", mode="before")
    @classmethod
    def ensure_path(cls, v: str) -> Path:
        p = Path(v)
        p.parent.mkdir(parents=True, exist_ok=True)
        return p


@lru_cache(maxsize=1)
def load_config(config_path: Path | None = None) -> Config:
    import yaml

    if config_path is None:
        config_path = Path(__file__).resolve().parent.parent.parent / "config.yaml"

    with open(config_path) as f:
        data = yaml.safe_load(f)

    return Config(**data)
