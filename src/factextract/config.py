from pathlib import Path
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
    data_dir: Path
    llm_model: str = "gemini/gemini-3.5-flash-lite"
    ingest: IngestConfig = IngestConfig()

    @field_validator("graph_db_path", "metadata_db_path", mode="before")
    @classmethod
    def ensure_parent_dir(cls, v):
        p = Path(v)
        p.parent.mkdir(parents=True, exist_ok=True)
        return p

    @field_validator("data_dir", mode="before")
    @classmethod
    def ensure_dir(cls, v):
        p = Path(v)
        p.mkdir(parents=True, exist_ok=True)
        return p


DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent.parent.parent / "config.yaml"

_config: Config | None = None


def load_config(config_path: Path | None = None) -> Config:
    """Build a fresh Config from disk. Always reads; no caching."""
    import yaml

    if config_path is None:
        config_path = DEFAULT_CONFIG_PATH

    with open(config_path) as f:
        data = yaml.safe_load(f)

    return Config(**data)


def init_config(config_path: Path | None = None) -> Config:
    """Construct the singleton. Call once at the entry point."""
    global _config
    _config = load_config(config_path)
    return _config


def set_config(config: Config) -> Config:
    """Replace the singleton. Used by the GUI settings editor."""
    global _config
    _config = config
    return _config


def get_config() -> Config:
    """Return the singleton; lazily constructs from default path on first call."""
    global _config
    if _config is None:
        init_config()
    assert _config is not None
    return _config
