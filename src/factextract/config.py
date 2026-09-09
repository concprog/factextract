from pathlib import Path
from pydantic import BaseModel, ConfigDict, Field, field_validator


class IngestConfig(BaseModel):
    model_config = ConfigDict(validate_by_alias=True, validate_by_name=True)

    header: bool = Field(default=False, alias="header")
    footer: bool = Field(default=False, alias="footer")
    table_strategy: str = Field(default="lines_strict", alias="table-strategy")
    tokenizer: str = Field(default="gpt2", alias="tokenizer")
    chunk_size: int = Field(default=8192, alias="chunk-size")
    chunk_overlap: int = Field(default=128, alias="chunk-overlap")
    min_sentences_per_chunk: int = Field(default=6, alias="min-sentences-per-chunk")


class Config(BaseModel):
    model_config = ConfigDict(validate_by_alias=True, validate_by_name=True)

    graph_db_path: Path = Field(alias="graph-db-path")
    metadata_db_path: Path = Field(alias="metadata-db-path")
    data_dir: Path = Field(alias="data-dir")
    llm_model: str = Field(default="openai/Qwen/Qwen3.6-27B-FP8", alias="llm-model")
    llm_base_url: str | None = Field(default=None, alias="llm-base-url")
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
