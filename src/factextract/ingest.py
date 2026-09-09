import pymupdf4llm
from chonkie import SentenceChunker

from .schema import Source
from .config import get_config


def glob() -> list[Source]:
    return [Source(file=p) for p in get_config().data_dir.rglob("*.pdf")]


def ingest(source: Source) -> list[str]:
    ic = get_config().ingest

    md = pymupdf4llm.to_markdown(
        str(source.file),
        header=ic.header,
        footer=ic.footer,
        table_strategy=ic.table_strategy,
    )

    chunker = SentenceChunker(
        tokenizer=ic.tokenizer,
        chunk_size=ic.chunk_size,
        chunk_overlap=ic.chunk_overlap,
        min_sentences_per_chunk=ic.min_sentences_per_chunk,
    )

    chunks = chunker.chunk(md)
    return [chunk.text for chunk in chunks]
