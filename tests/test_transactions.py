"""Transaction logging (blueprint §12) — every resolved analysis accumulates as gold data, with the
eval_fixture contamination flag, on by default, and never breaking serving if logging fails."""
import asyncio
import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import thamizh_mcp.config as config
import thamizh_mcp.core.engine as eng
from thamizh_mcp.core.engine import Engine
from thamizh_mcp.store.knowledge import KnowledgeStore


def _txns(db):
    con = sqlite3.connect(db)
    try:
        return con.execute(
            "SELECT tool, word, normalized, eval_fixture, analysis_json FROM transactions").fetchall()
    finally:
        con.close()


def _engine(db, fixtures=frozenset()):
    e = Engine(store=KnowledgeStore(db))
    e._fixtures = fixtures   # pin so the test doesn't depend on the data file
    return e


def test_analyze_logs_full_gold_record(tmp_path):
    db = tmp_path / "k.sqlite3"
    a = asyncio.run(_engine(db, frozenset({"மரம்"})).analyze("மரம்", "மரம்"))
    rows = _txns(db)
    assert len(rows) == 1
    tool, word, norm, fixture, payload = rows[0]
    assert tool == "analyze_word" and norm == "மரம்" and fixture == 1
    assert json.loads(payload)["word"] == "மரம்"       # full WordAnalysis round-trips


def test_non_fixture_word_not_flagged(tmp_path):
    db = tmp_path / "k.sqlite3"
    asyncio.run(_engine(db, frozenset({"மரம்"})).analyze("தமிழ்", "தமிழ்"))
    assert _txns(db)[0][3] == 0


def test_tool_label_from_focused_entry_point(tmp_path, monkeypatch):
    db = tmp_path / "k.sqlite3"
    monkeypatch.setattr(eng, "_default", _engine(db))
    asyncio.run(eng.get_root("மரம்", "மரம்"))
    assert _txns(db)[0][0] == "get_root"


def test_logging_can_be_disabled(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "TXN_LOG", False)
    db = tmp_path / "k.sqlite3"
    e = _engine(db)
    asyncio.run(e.analyze("மரம்", "மரம்"))
    assert asyncio.run(e.store.transaction_stats())["transactions"] == 0


def test_logging_is_non_fatal(tmp_path):
    store = KnowledgeStore(tmp_path / "k.sqlite3")
    async def boom(**kw):
        raise RuntimeError("simulated disk-full")
    store.log_transaction = boom
    a = asyncio.run(Engine(store=store).analyze("மரம்", "மரம்"))   # must not raise
    assert a.word == "மரம்"


def test_no_store_is_fine():
    a = asyncio.run(Engine().analyze("மரம்", "மரம்"))
    assert a.word == "மரம்"


def test_config_loads_the_fixture_registry():
    words = config.eval_fixture_words()
    assert {"மரம்", "புத்தகம்", "ஜிலேபி"} <= words   # from data/eval_fixtures.json


def test_transaction_stats(tmp_path):
    db = tmp_path / "k.sqlite3"
    e = _engine(db, frozenset({"மரம்"}))
    asyncio.run(e.analyze("மரம்", "மரம்"))
    asyncio.run(e.analyze("மரம்", "மரம்"))
    asyncio.run(e.analyze("தமிழ்", "தமிழ்"))
    st = asyncio.run(e.store.transaction_stats())
    assert st == {"transactions": 3, "distinct_words": 2, "eval_fixture_rows": 2}
