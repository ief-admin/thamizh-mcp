"""SQLite knowledge store — the self-enriching layer (blueprint §5).

Per-claim provenance: one row per (word, field, source). Writes are serialized
(asyncio lock + single connection, WAL). FST morphology never caches here — this store
exists for the lexical/etymology/meaning/equivalent layers, where coverage must grow.
"""
from __future__ import annotations

import asyncio
import json
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import anyio

_SCHEMA = Path(__file__).with_name("schema.sql").read_text("utf-8")


@dataclass
class Claim:
    field: str
    value: Any                      # JSON-serializable schema fragment
    source: str
    tier: str                       # anchor | evolving
    retrieved: str                  # ISO date (evolving) or version pin (anchor)
    authority: Optional[str] = None
    confidence: Optional[float] = None


class KnowledgeStore:
    def __init__(self, db_path: Path | str):
        self.db_path = Path(db_path)
        self._conn: Optional[sqlite3.Connection] = None
        self._write_lock = asyncio.Lock()

    def _connect(self) -> sqlite3.Connection:
        if self._conn is None:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.executescript(_SCHEMA)
        return self._conn

    # -- sync core (runs in worker thread) --
    def _get(self, word: str, field_name: Optional[str]) -> list[Claim]:
        conn = self._connect()
        sql = "SELECT field, value_json, source, tier, authority, confidence, retrieved FROM claims WHERE word=?"
        args: list = [word]
        if field_name:
            sql += " AND field=?"
            args.append(field_name)
        return [
            Claim(field=r[0], value=json.loads(r[1]), source=r[2], tier=r[3],
                  authority=r[4], confidence=r[5], retrieved=r[6])
            for r in conn.execute(sql, args)
        ]

    def _put(self, word: str, claims: list[Claim]) -> None:
        conn = self._connect()
        with conn:
            conn.executemany(
                "INSERT OR REPLACE INTO claims (word, field, value_json, source, tier, authority, confidence, retrieved)"
                " VALUES (?,?,?,?,?,?,?,?)",
                [(word, c.field, json.dumps(c.value, ensure_ascii=False), c.source, c.tier,
                  c.authority, c.confidence, c.retrieved) for c in claims],
            )

    def _stale(self, cutoff_iso: str, tier: str) -> list[str]:
        conn = self._connect()
        rows = conn.execute(
            "SELECT DISTINCT word FROM claims WHERE tier=? AND retrieved < ? ORDER BY word",
            (tier, cutoff_iso))
        return [r[0] for r in rows]

    # -- async API --
    async def get_claims(self, normalized_word: str, field_name: Optional[str] = None) -> list[Claim]:
        return await anyio.to_thread.run_sync(self._get, normalized_word, field_name)

    async def stale_words(self, max_age_days: int, tier: str = "evolving") -> list[str]:
        """Words holding a `tier` claim retrieved more than max_age_days ago (ISO-date compare).
        Anchor claims store a version pin, not a date, so only the evolving tier is meaningful here."""
        import datetime as _dt
        cutoff = (_dt.date.today() - _dt.timedelta(days=max_age_days)).isoformat()
        return await anyio.to_thread.run_sync(self._stale, cutoff, tier)

    async def put_claims(self, normalized_word: str, claims: list[Claim]) -> None:
        async with self._write_lock:  # serialize writes — SQLite is single-writer
            await anyio.to_thread.run_sync(self._put, normalized_word, claims)

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None
