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


class FakeMorph(SourceAdapter):
    name, tier = "ThamizhiMorph", "anchor"
    async def lookup(self, w):
        return AdapterResult(fields={"all_analyses": [
            MorphAnalysis(lemma="மரம்", pos="noun", tags=["infInc", "loc"])]},
            sources=[SourceRef(name="ThamizhiMorph", tier="anchor")], tier="anchor")


class FakeMeaning(SourceAdapter):
    name, tier = "Tamil Wiktionary", "evolving"
    async def lookup(self, w):
        return AdapterResult(
            fields={"senses": [{"gloss_ta": "ஒரு வகை தாவரம்", "citation": "https://ta.wiktionary.org/x"}]},
            sources=[SourceRef(name=self.name, tier="evolving", retrieved="2026-07-02")], tier="evolving")


def test_all_five_tools_registered():
    names = {t.name for t in asyncio.run(server.mcp.list_tools())}
    assert {"analyze_word", "suggest_native_equivalent", "classify_origin",
            "get_root", "get_meaning"} <= names


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


needs_fst = pytest.mark.skipif(not config.flookup_available(),
                               reason="flookup/FSTs not on this machine (see data/PINS.md)")


@needs_fst
def test_get_root_live_fst(monkeypatch):
    from thamizh_mcp.adapters.thamizhimorph import ThamizhiMorphAdapter
    monkeypatch.setattr(eng, "_default", Engine(morph=ThamizhiMorphAdapter()))
    out = json.loads(asyncio.run(server.get_root(server.GetRootInput(word="மரத்தில்"))))
    assert any(m["lemma"] == "மரம்" for m in out["all_analyses"])
