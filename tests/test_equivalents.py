"""Indic-To-Pure-Tamil equivalents adapter (objective 5) + engine wiring.

Fully offline: synthetic CSVs for the merge/attribution/ordering contract, plus a light smoke
test against the real vendored lists. No network, no foma — runs in the 25-without-foma tier.
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from thamizh_mcp import config
from thamizh_mcp.adapters.base import AdapterResult, NoEntry
from thamizh_mcp.adapters.equivalents import IndicToPureTamilAdapter, load_index
from thamizh_mcp.core.engine import Engine


def _write(dir_: Path, name: str, rows: list[tuple[str, str]]) -> None:
    lines = ["INDIC,TAMIL"]
    for indic, tamil in rows:
        cell = f'"{tamil}"' if "," in tamil else tamil
        lines.append(f"{indic},{cell}")
    (dir_ / name).write_text("\n".join(lines) + "\n", encoding="utf-8")


def _fixture_dir(tmp_path: Path) -> tuple[Path, tuple[str, ...]]:
    _write(tmp_path, "viruba.csv", [("அகங்காரம்", "செருக்கு, இறுமாப்பு"), ("அகராதி", "அகரமுதலி, அகரவரிசை")])
    _write(tmp_path, "tamilchol.csv", [("அகராதி", "அகரவரிசை")])  # அகரவரிசை attested by 2 lists
    return tmp_path, ("viruba.csv", "tamilchol.csv")


# --- index / merge contract ---

def test_index_unions_attesting_lists_and_dedupes(tmp_path):
    data_dir, sublists = _fixture_dir(tmp_path)
    index = load_index(data_dir, sublists)
    assert "அகராதி" in index
    entry = index["அகராதி"]
    assert entry["அகரவரிசை"] == ["viruba", "tamilchol"]  # unioned across both lists
    assert entry["அகரமுதலி"] == ["viruba"]


def test_missing_sublist_is_skipped_not_fatal(tmp_path):
    _write(tmp_path, "viruba.csv", [("அகராதி", "அகரவரிசை")])
    index = load_index(tmp_path, ("viruba.csv", "does-not-exist.csv"))
    assert list(index) == ["அகராதி"]


# --- adapter lookup ---

def test_hit_returns_sourced_attested_candidates_ordered(tmp_path):
    data_dir, sublists = _fixture_dir(tmp_path)
    res = asyncio.run(IndicToPureTamilAdapter(data_dir, sublists).lookup("அகராதி"))
    assert isinstance(res, AdapterResult)
    cands = res.fields["candidates"]
    # every candidate carries a source + attestation — the hard rule
    assert all(c["source"] == "Indic-To-Pure-Tamil" and c["attestation"] == "attested" for c in cands)
    # most-attested first: அகரவரிசை (2 lists) precedes single-list equivalents
    assert cands[0]["equivalent"] == "அகரவரிசை"
    assert "viruba" in cands[0]["citation"] and "tamilchol" in cands[0]["citation"]
    assert res.sources[0].tier == "evolving"


def test_miss_is_honest_noentry(tmp_path):
    data_dir, sublists = _fixture_dir(tmp_path)
    res = asyncio.run(IndicToPureTamilAdapter(data_dir, sublists).lookup("மரம்"))
    assert isinstance(res, NoEntry) and res.reason == "no_entry"


# --- engine wiring ---

def test_engine_hit_surfaces_applicable_equivalents(tmp_path):
    data_dir, sublists = _fixture_dir(tmp_path)
    e = Engine(equivalent_sources=[IndicToPureTamilAdapter(data_dir, sublists)])
    a = asyncio.run(e.analyze("அகராதி", "அகராதி", include=["native_equivalent"]))
    assert a.native_equivalent.applicable is True
    assert a.native_equivalent.candidates[0].equivalent == "அகரவரிசை"
    assert a.native_equivalent.candidates[0].attestation == "attested"
    assert not any(g.field == "native_equivalent" for g in a.gaps)  # a hit is not a gap


def test_engine_miss_is_applicable_false_with_gap(tmp_path):
    data_dir, sublists = _fixture_dir(tmp_path)
    e = Engine(equivalent_sources=[IndicToPureTamilAdapter(data_dir, sublists)])
    a = asyncio.run(e.analyze("மரம்", "மரம்", include=["native_equivalent"]))
    assert a.native_equivalent.applicable is False
    assert any(g.field == "native_equivalent" for g in a.gaps)


def test_engine_no_source_still_gaps():
    a = asyncio.run(Engine().analyze("அகராதி", "அகராதி", include=["native_equivalent"]))
    assert a.native_equivalent.applicable is False
    assert any(g.field == "native_equivalent" for g in a.gaps)


# --- real vendored data smoke test ---

def test_real_i2pt_known_hit_and_miss():
    ad = IndicToPureTamilAdapter()  # real config.EQUIVALENTS_DIR
    hit = asyncio.run(ad.lookup("அகராதி"))
    assert isinstance(hit, AdapterResult) and hit.fields["candidates"]
    assert all(c["source"] and c["attestation"] == "attested" for c in hit.fields["candidates"])
    miss = asyncio.run(ad.lookup("மரம்"))
    assert isinstance(miss, NoEntry)
