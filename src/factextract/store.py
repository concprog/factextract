import sqlite3
from datetime import datetime
from functools import wraps
from pathlib import Path

from factextract.schema import Source, Fact, Island
from factextract.config import load_config


def _connect() -> sqlite3.Connection:
    config = load_config()
    conn = sqlite3.connect(config.metadata_db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def with_conn(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        conn = _connect()
        try:
            result = func(conn, *args, **kwargs)
            conn.commit()
            return result
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
    return wrapper


def _source_from_row(row) -> Source:
    return Source(file=Path(row["file"]))


def _fact_from_row(conn, row) -> Fact:
    source_row = conn.execute(
        "SELECT * FROM sources WHERE hash = ?", (row["source_hash"],)
    ).fetchone()
    return Fact(
        content=row["content"],
        source=_source_from_row(source_row),
        time=datetime.fromisoformat(row["time"]),
        window=int(row["window_seconds"]),
    )


def _island_from_row(conn, row) -> Island:
    fact_id_rows = conn.execute(
        "SELECT fact_id FROM island_fact WHERE island_id = ?", (row["id"],)
    ).fetchall()
    return Island(
        relation_type=row["relation_type"],
        reason=row["reason"],
        fact_ids=[r["fact_id"] for r in fact_id_rows],
    )


def init_db() -> None:
    conn = _connect()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS sources (
            hash TEXT PRIMARY KEY,
            file TEXT NOT NULL,
            title TEXT NOT NULL
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
        CREATE INDEX IF NOT EXISTS idx_facts_end ON facts(unixepoch(time) + window_seconds);

        CREATE TABLE IF NOT EXISTS islands (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            relation_type TEXT NOT NULL,
            reason TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS island_fact (
            island_id INTEGER NOT NULL REFERENCES islands(id) ON DELETE CASCADE,
            fact_id TEXT NOT NULL REFERENCES facts(hash) ON DELETE CASCADE,
            PRIMARY KEY (island_id, fact_id)
        ) WITHOUT ROWID;

        CREATE INDEX IF NOT EXISTS idx_island_fact_fact ON island_fact(fact_id, island_id);
    """)
    conn.close()


@with_conn
def store_sources(conn, sources: list[Source]) -> list[str]:
    conn.executemany(
        "INSERT OR IGNORE INTO sources (hash, file, title) VALUES (?, ?, ?)",
        [(s.hash, str(s.file), s.title) for s in sources],
    )
    return [s.hash for s in sources]


@with_conn
def store_facts(conn, facts: list[Fact]) -> list[str]:
    conn.executemany(
        "INSERT OR IGNORE INTO facts (hash, content, source_hash, time, window_seconds) VALUES (?, ?, ?, ?, ?)",
        [
            (f.hash, f.content, f.source.hash, f.time.isoformat(), f.window)
            for f in facts
        ],
    )
    return [f.hash for f in facts]


@with_conn
def store_islands(conn, islands: list[Island]) -> list[int]:
    ids = []
    for island in islands:
        cursor = conn.execute(
            "INSERT INTO islands (relation_type, reason) VALUES (?, ?)",
            (island.relation_type, island.reason),
        )
        island_id = cursor.lastrowid
        conn.executemany(
            "INSERT OR IGNORE INTO island_fact (island_id, fact_id) VALUES (?, ?)",
            [(island_id, fid) for fid in island.fact_ids],
        )
        ids.append(island_id)
    return ids


@with_conn
def store_or_update_sources(conn, sources: list[Source]) -> list[str]:
    conn.executemany(
        "INSERT OR REPLACE INTO sources (hash, file, title) VALUES (?, ?, ?)",
        [(s.hash, str(s.file), s.title) for s in sources],
    )
    return [s.hash for s in sources]


@with_conn
def store_or_update_facts(conn, facts: list[Fact]) -> list[str]:
    conn.executemany(
        "INSERT OR REPLACE INTO facts (hash, content, source_hash, time, window_seconds) VALUES (?, ?, ?, ?, ?)",
        [
            (f.hash, f.content, f.source.hash, f.time.isoformat(), f.window)
            for f in facts
        ],
    )
    return [f.hash for f in facts]


@with_conn
def store_or_update_islands(conn, islands: list[Island]) -> list[int]:
    ids = []
    for island in islands:
        existing = conn.execute(
            "SELECT id FROM islands WHERE relation_type = ? AND reason = ?",
            (island.relation_type, island.reason),
        ).fetchone()
        if existing:
            island_id = existing[0]
            conn.execute(
                "DELETE FROM island_fact WHERE island_id = ?", (island_id,)
            )
        else:
            cursor = conn.execute(
                "INSERT INTO islands (relation_type, reason) VALUES (?, ?)",
                (island.relation_type, island.reason),
            )
            island_id = cursor.lastrowid
        conn.executemany(
            "INSERT OR IGNORE INTO island_fact (island_id, fact_id) VALUES (?, ?)",
            [(island_id, fid) for fid in island.fact_ids],
        )
        ids.append(island_id)
    return ids


@with_conn
def get_all_sources(conn) -> list[Source]:
    rows = conn.execute("SELECT * FROM sources").fetchall()
    return [_source_from_row(row) for row in rows]


@with_conn
def get_all_facts(conn) -> list[Fact]:
    rows = conn.execute("SELECT * FROM facts").fetchall()
    return [_fact_from_row(conn, row) for row in rows]


@with_conn
def get_fact_ids(conn) -> list[str]:
    rows = conn.execute("SELECT hash FROM facts").fetchall()
    return [row["hash"] for row in rows]


@with_conn
def get_all_islands(conn) -> list[Island]:
    rows = conn.execute("SELECT * FROM islands").fetchall()
    return [_island_from_row(conn, row) for row in rows]


@with_conn
def get_facts_in_island(conn, island_id: int) -> list[Fact]:
    rows = conn.execute(
        "SELECT f.* FROM facts f "
        "JOIN island_fact if ON f.hash = if.fact_id "
        "WHERE if.island_id = ?",
        (island_id,),
    ).fetchall()
    return [_fact_from_row(conn, row) for row in rows]


@with_conn
def get_islands_with_fact(conn, fact_id: str) -> list[Island]:
    rows = conn.execute(
        "SELECT i.* FROM islands i "
        "JOIN island_fact if ON i.id = if.island_id "
        "WHERE if.fact_id = ?",
        (fact_id,),
    ).fetchall()
    return [_island_from_row(conn, row) for row in rows]


@with_conn
def get_facts_valid_at(conn, at: datetime) -> list[Fact]:
    at_epoch = int(at.timestamp())
    rows = conn.execute(
        "SELECT * FROM facts "
        "WHERE unixepoch(time) <= ? "
        "AND unixepoch(time) + window_seconds >= ?",
        (at_epoch, at_epoch),
    ).fetchall()
    return [_fact_from_row(conn, row) for row in rows]


@with_conn
def get_timestamps(conn) -> list[datetime]:
    rows = conn.execute("SELECT DISTINCT time FROM facts ORDER BY time").fetchall()
    return [datetime.fromisoformat(row["time"]) for row in rows]


@with_conn
def get_overlapping_facts(conn) -> list[tuple[Fact, Fact]]:
    rows = conn.execute(
        "SELECT a.*, b.* FROM facts a "
        "JOIN facts b ON a.hash < b.hash "
        "WHERE unixepoch(a.time) <= unixepoch(b.time) + b.window_seconds "
        "AND unixepoch(b.time) <= unixepoch(a.time) + a.window_seconds"
    ).fetchall()
    result = []
    for row in rows:
        # left half = fact a, right half = fact b
        cols = row.keys()
        half = len(cols) // 2
        a_row = {cols[i]: row[cols[i]] for i in range(half)}
        b_row = {cols[i]: row[cols[i]] for i in range(half, len(cols))}
        result.append((_fact_from_row(conn, a_row), _fact_from_row(conn, b_row)))
    return result


@with_conn
def get_islands_with_facts(conn) -> list[tuple[Island, list[Fact]]]:
    rows = conn.execute("SELECT * FROM islands").fetchall()
    result = []
    for row in rows:
        island = _island_from_row(conn, row)
        facts = get_facts_in_island(row["id"])
        result.append((island, facts))
    return result


@with_conn
def get_unaffiliated_facts(conn) -> list[Fact]:
    rows = conn.execute(
        "SELECT f.* FROM facts f "
        "LEFT JOIN island_fact IF ON f.hash = IF.fact_id "
        "WHERE IF.fact_id IS NULL"
    ).fetchall()
    return [_fact_from_row(conn, row) for row in rows]
