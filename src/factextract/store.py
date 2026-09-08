import sqlite3
import json
from datetime import datetime

from factextract.schema import Source, Fact, Island
from factextract.config import load_config


def _connect() -> sqlite3.Connection:
    config = load_config()
    conn = sqlite3.connect(config.metadata_db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db() -> None:
    conn = _connect()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS sources (
            hash TEXT PRIMARY KEY,
            file TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS facts (
            hash TEXT PRIMARY KEY,
            content TEXT NOT NULL,
            source_hash TEXT NOT NULL REFERENCES sources(hash),
            time TEXT NOT NULL,
            window_seconds REAL NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_facts_time ON facts(time);
        CREATE INDEX IF NOT EXISTS idx_facts_source ON facts(source_hash);

        CREATE TABLE IF NOT EXISTS islands (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fact_ids TEXT NOT NULL,
            relation_type TEXT NOT NULL
        );
    """)
    conn.close()


def store_source(source: Source) -> str:
    conn = _connect()
    conn.execute(
        "INSERT OR IGNORE INTO sources (hash, file) VALUES (?, ?)",
        (source.hash, str(source.file)),
    )
    conn.commit()
    conn.close()
    return source.hash


def store_fact(fact: Fact) -> str:
    conn = _connect()
    conn.execute(
        "INSERT OR IGNORE INTO facts (hash, content, source_hash, time, window_seconds) VALUES (?, ?, ?, ?, ?)",
        (
            fact.hash,
            fact.content,
            fact.source.hash,
            fact.time.isoformat(),
            fact.window.total_seconds(),
        ),
    )
    conn.commit()
    conn.close()
    return fact.hash


def store_island(island: Island) -> int:
    conn = _connect()
    cursor = conn.execute(
        "INSERT INTO islands (fact_ids, relation_type) VALUES (?, ?)",
        (json.dumps(island.fact_ids), island.relation_type),
    )
    island_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return island_id


def get_facts_by_date(start: datetime, end: datetime) -> list[dict]:
    conn = _connect()
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT * FROM facts WHERE time BETWEEN ? AND ?",
        (start.isoformat(), end.isoformat()),
    ).fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_facts_by_hash(hashes: list[str]) -> list[dict]:
    conn = _connect()
    conn.row_factory = sqlite3.Row
    placeholders = ",".join("?" for _ in hashes)
    rows = conn.execute(
        f"SELECT * FROM facts WHERE hash IN ({placeholders})",
        hashes,
    ).fetchall()
    conn.close()
    return [dict(row) for row in rows]


def search_facts_by_hash(pattern: str) -> list[dict]:
    conn = _connect()
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT * FROM facts WHERE hash LIKE ?",
        (f"%{pattern}%",),
    ).fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_sources_by_hash(hashes: list[str]) -> list[dict]:
    conn = _connect()
    conn.row_factory = sqlite3.Row
    placeholders = ",".join("?" for _ in hashes)
    rows = conn.execute(
        f"SELECT * FROM sources WHERE hash IN ({placeholders})",
        hashes,
    ).fetchall()
    conn.close()
    return [dict(row) for row in rows]


def search_sources_by_hash(pattern: str) -> list[dict]:
    conn = _connect()
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT * FROM sources WHERE hash LIKE ?",
        (f"%{pattern}%",),
    ).fetchall()
    conn.close()
    return [dict(row) for row in rows]
