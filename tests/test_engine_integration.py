"""Engine composition: anchor fill, enrichment loop (pull → write-back → cache hit), honest gaps."""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from thamizh_mcp.adapters.base import AdapterResult, NoEntry, SourceAdapter
from thamizh_mcp.core.engine import Engine
from thamizh_mcp.schema import MorphAnalysis, SourceRef
from thamizh_mcp.store.knowledge import KnowledgeStore

MORPH_SRC = SourceRef(name="ThamizhiMorph", tier="anchor", retrieved="pin@test")


class FakeMorph(SourceAdapter):
    name, tier = "ThamizhiMorph", "anchor"
    async def lookup(self, w):
        return AdapterResult(fields={"all_analyses": [
            MorphAnalysis(lemma="மரம்", pos="noun", tags=["infInc", "loc"]),
            MorphAnalysis(lemma="மரம்", pos="noun", tags=["infInc", "soc"])]},
            sources=[MORPH_SRC], tier="anchor")


class FakeWiktionary(SourceAdapter):
    name, tier = "Tamil Wiktionary", "evolving"
    calls = 0
    async def lookup(self, w):
        FakeWiktionary.calls += 1
        return AdapterResult(fields={"senses": [{"gloss_ta": "ஒரு வகை தாவரம்", "citation": "https://ta.wiktionary.org/wiki/x"}]},
                             sources=[SourceRef(name=self.name, tier="evolving", retrieved="2026-07-02")],
                             tier="evolving")


class DeadSource(SourceAdapter):
    name, tier = "Dead", "evolving"
    async def lookup(self, w):
        return NoEntry(source=self.name, reason="timeout", note="simulated")


def test_morphology_fills_grounded_fields_and_keeps_ambiguity():
    a = asyncio.run(Engine(morph=FakeMorph()).analyze("மரத்தில்", "மரத்தில்"))
    assert a.lemma == "மரம்" and a.pos == "பெயர்ச்சொல்"
    assert len(a.all_analyses) == 2                       # both analyses kept
    assert a.grammar.word_class == "பெயர்" and a.grammar.authority == "Tholkappiyam"
    assert a.grammar.case is None and "ambiguous" in a.grammar.notes  # loc vs soc — not adjudicated
    assert any(s.name == "ThamizhiMorph" and s.tier == "anchor" for s in a.sources)
    # native FST parse + no non-native markers → இயற்சொல்; equivalent then correctly not applicable
    assert a.origin.class_ == "இயற்சொல்" and a.origin.is_native is True
    assert a.native_equivalent.applicable is False
    assert {g.field for g in a.gaps} == {"formation", "meaning"}  # origin resolved, not a gap


def test_enrichment_loop_pull_writeback_then_cache(tmp_path):
    async def go():
        store = KnowledgeStore(tmp_path / "k.sqlite3")
        FakeWiktionary.calls = 0
        e = Engine(morph=FakeMorph(), meaning_sources=[FakeWiktionary()], store=store)
        a1 = await e.analyze("மரம்", "மரம்")
        assert a1.meaning.senses[0].gloss_ta == "ஒரு வகை தாவரம்"
        assert FakeWiktionary.calls == 1
        a2 = await e.analyze("மரம்", "மரம்")             # second ask → served from store
        assert a2.meaning.senses[0].gloss_ta == "ஒரு வகை தாவரம்"
        assert FakeWiktionary.calls == 1                  # no second pull — self-enriched
        assert a2.meaning.sources[0].name == "Tamil Wiktionary"
        store.close()
    asyncio.run(go())


def test_dead_source_yields_gap_with_reason():
    a = asyncio.run(Engine(meaning_sources=[DeadSource()]).analyze("மரம்", "மரம்", include=["meaning"]))
    assert a.meaning.senses == []
    gap = next(g for g in a.gaps if g.field == "meaning")
    assert "Dead: timeout — simulated" in gap.note   # failure reason must surface


def test_enrichment_disabled_never_pulls():
    FakeWiktionary.calls = 0
    a = asyncio.run(Engine(meaning_sources=[FakeWiktionary()]).analyze(
        "மரம்", "மரம்", include=["meaning"], allow_enrichment=False))
    assert FakeWiktionary.calls == 0 and any(g.field == "meaning" for g in a.gaps)
