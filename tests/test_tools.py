"""Thin MCP heads get_root / get_meaning: registration, serialization, honest gaps, errors.

Serialization is tested against injected fake engines (monkeypatched default) so these run
offline with no network or store; one live test exercises the real FST path.
"""
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pytest

import thamizh_mcp.core.engine as eng
from thamizh_mcp import config, server
from thamizh_mcp.adapters.base import AdapterResult, SourceAdapter
from thamizh_mcp.core.engine import Engine
from thamizh_mcp.schema import MorphAnalysis, SourceRef
from thamizh_mcp.store.knowledge import Claim, KnowledgeStore


class FakeMorph(SourceAdapter):
    name, tier = "ThamizhiMorph", "anchor"
    async def lookup(self, w):
        return AdapterResult(fields={"all_analyses": [
            MorphAnalysis(lemma="மரம்", pos="noun", tags=["infInc", "loc"])]},
            sources=[SourceRef(name="ThamizhiMorph", tier="anchor")], tier="anchor")


class FakeMeaning(SourceAdapter):
    name, tier = "Tamil Wiktionary", "evolving"
    calls = 0
    async def lookup(self, w):
        FakeMeaning.calls += 1
        return AdapterResult(
            fields={"senses": [{"gloss_ta": "ஒரு வகை தாவரம்", "citation": "https://ta.wiktionary.org/x"}]},
            sources=[SourceRef(name=self.name, tier="evolving", retrieved="2026-07-02")], tier="evolving")


def test_all_six_tools_registered():
    names = {t.name for t in asyncio.run(server.mcp.list_tools())}
    assert {"analyze_word", "suggest_native_equivalent", "classify_origin",
            "get_root", "get_meaning", "enrich_word"} <= names


# --- get_root ---

def test_get_root_serializes_lemma_and_analyses(monkeypatch):
    monkeypatch.setattr(eng, "_default", Engine(morph=FakeMorph()))
    out = json.loads(asyncio.run(server.get_root(server.GetRootInput(word="மரத்தில்"))))
    assert out["lemma"] == "மரம்" and out["pos"] == "பெயர்ச்சொல்"
    assert out["all_analyses"] and out["all_analyses"][0]["lemma"] == "மரம்"


def test_get_root_no_fst_is_honest_gap(monkeypatch):
    monkeypatch.setattr(eng, "_default", Engine(morph=None))   # no FST wired
    out = json.loads(asyncio.run(server.get_root(server.GetRootInput(word="மரம்"))))
    assert out["lemma"] == "" and any(g["field"] == "lemma" for g in out["gaps"])


def test_get_root_rejects_non_tamil():
    assert asyncio.run(server.get_root(server.GetRootInput(word="tree"))).startswith("Error:")


# --- get_meaning ---

def test_get_meaning_serializes_senses(monkeypatch):
    monkeypatch.setattr(eng, "_default", Engine(meaning_sources=[FakeMeaning()]))
    out = json.loads(asyncio.run(server.get_meaning(server.GetMeaningInput(word="மரம்"))))
    assert out["meaning"]["senses"][0]["gloss_ta"] == "ஒரு வகை தாவரம்"
    assert out["meaning"]["sources"][0]["name"] == "Tamil Wiktionary"


def test_get_meaning_disabled_enrichment_is_honest_gap(monkeypatch):
    monkeypatch.setattr(eng, "_default", Engine(meaning_sources=[FakeMeaning()]))
    out = json.loads(asyncio.run(
        server.get_meaning(server.GetMeaningInput(word="மரம்", allow_enrichment=False))))
    assert out["meaning"]["senses"] == []
    gap = next(g for g in out["gaps"] if g["field"] == "meaning")
    assert "enrichment disabled" in gap["note"]


def test_get_meaning_rejects_non_tamil():
    assert asyncio.run(server.get_meaning(server.GetMeaningInput(word="tree"))).startswith("Error:")


# --- enrich_word ---

def test_enrich_word_caches_and_is_idempotent(monkeypatch, tmp_path):
    monkeypatch.setattr(eng, "_default",
                        Engine(meaning_sources=[FakeMeaning()], store=KnowledgeStore(tmp_path / "k.sqlite3")))
    FakeMeaning.calls = 0
    out1 = json.loads(asyncio.run(server.enrich_word(server.EnrichWordInput(word="மரம்"))))
    cached = {c["field"]: c for c in out1["cached_claims"]}
    assert "meaning" in cached and cached["meaning"]["source"] == "Tamil Wiktionary"
    assert cached["meaning"]["tier"] == "evolving"
    assert FakeMeaning.calls == 1
    out2 = json.loads(asyncio.run(server.enrich_word(server.EnrichWordInput(word="மரம்"))))
    assert [c["field"] for c in out2["cached_claims"]] == ["meaning"]   # still cached
    assert FakeMeaning.calls == 1                                        # served from store, no re-pull


def test_enrich_word_no_store_reports_nothing_cached(monkeypatch):
    monkeypatch.setattr(eng, "_default", Engine(meaning_sources=[FakeMeaning()]))  # no store
    out = json.loads(asyncio.run(server.enrich_word(server.EnrichWordInput(word="மரம்"))))
    assert out["cached_claims"] == []


def test_enrich_word_rejects_bad_include(monkeypatch, tmp_path):
    monkeypatch.setattr(eng, "_default", Engine(store=KnowledgeStore(tmp_path / "k.sqlite3")))
    err = asyncio.run(server.enrich_word(server.EnrichWordInput(word="மரம்", include=["bogus"])))
    assert err.startswith("Error:") and "bogus" in err


def test_enrich_word_rejects_non_tamil():
    assert asyncio.run(server.enrich_word(server.EnrichWordInput(word="tree"))).startswith("Error:")


# --- refresh_sources ---

def _refresh_engine(tmp_path):
    return Engine(meaning_sources=[FakeMeaning()], store=KnowledgeStore(tmp_path / "k.sqlite3"))


def test_refresh_words_batch(monkeypatch, tmp_path):
    monkeypatch.setattr(eng, "_default", _refresh_engine(tmp_path))
    FakeMeaning.calls = 0
    out = json.loads(asyncio.run(server.refresh_sources(server.RefreshSourcesInput(words=["மரம்", "புத்தகம்"]))))
    assert out["refreshed_count"] == 2 and FakeMeaning.calls == 2
    assert all(any(f["field"] == "meaning" for f in r["refreshed"]) for r in out["results"])


def test_refresh_forces_repull_unlike_enrich(monkeypatch, tmp_path):
    monkeypatch.setattr(eng, "_default", _refresh_engine(tmp_path))
    FakeMeaning.calls = 0
    asyncio.run(server.refresh_sources(server.RefreshSourcesInput(words=["மரம்"])))
    asyncio.run(server.refresh_sources(server.RefreshSourcesInput(words=["மரம்"])))
    assert FakeMeaning.calls == 2   # forced re-pull each time (enrich would have stayed at 1)


def test_refresh_stale_days_selects_old_claims(monkeypatch, tmp_path):
    store = KnowledgeStore(tmp_path / "k.sqlite3")
    asyncio.run(store.put_claims("மரம்", [Claim(
        field="meaning", value={"senses": []}, source="old", tier="evolving", retrieved="2020-01-01")]))
    assert asyncio.run(store.stale_words(1)) == ["மரம்"]
    monkeypatch.setattr(eng, "_default", Engine(meaning_sources=[FakeMeaning()], store=store))
    FakeMeaning.calls = 0
    out = json.loads(asyncio.run(server.refresh_sources(server.RefreshSourcesInput(stale_days=1))))
    assert out["refreshed_count"] == 1 and FakeMeaning.calls == 1


def test_refresh_limit_bounds_work(monkeypatch, tmp_path):
    monkeypatch.setattr(eng, "_default", _refresh_engine(tmp_path))
    FakeMeaning.calls = 0
    out = json.loads(asyncio.run(
        server.refresh_sources(server.RefreshSourcesInput(words=["மரம்", "புத்தகம்", "வீடு"], limit=2))))
    assert out["refreshed_count"] == 2 and FakeMeaning.calls == 2


def test_refresh_requires_a_scope():
    assert asyncio.run(server.refresh_sources(server.RefreshSourcesInput())).startswith("Error:")


def test_refresh_reports_invalid_word_without_failing(monkeypatch, tmp_path):
    monkeypatch.setattr(eng, "_default", _refresh_engine(tmp_path))
    out = json.loads(asyncio.run(server.refresh_sources(server.RefreshSourcesInput(words=["tree", "மரம்"]))))
    errs = [r for r in out["results"] if r.get("error")]
    assert len(errs) == 1 and errs[0]["word"] == "tree" and out["refreshed_count"] == 1


needs_fst = pytest.mark.skipif(not config.flookup_available(),
                               reason="flookup/FSTs not on this machine (see data/PINS.md)")


@needs_fst
def test_get_root_live_fst(monkeypatch):
    from thamizh_mcp.adapters.thamizhimorph import ThamizhiMorphAdapter
    monkeypatch.setattr(eng, "_default", Engine(morph=ThamizhiMorphAdapter()))
    out = json.loads(asyncio.run(server.get_root(server.GetRootInput(word="மரத்தில்"))))
    assert any(m["lemma"] == "மரம்" for m in out["all_analyses"])
