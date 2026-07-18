"""Formation decoder (பகுபத உறுப்பு) + verb grammar (tense/முற்று) + explain_* tools.

Decoder rules are pure: MorphAnalysis in → Formation out, so most tests run without foma. One
live test exercises the real FST path.
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
from thamizh_mcp.core import decoder
from thamizh_mcp.core.engine import Engine
from thamizh_mcp.schema import MorphAnalysis, SourceRef


def _mk(word, analyses):
    class _Fake(SourceAdapter):
        name, tier = "ThamizhiMorph", "anchor"
        async def lookup(self, w):
            return AdapterResult(fields={"all_analyses": analyses},
                                 sources=[SourceRef(name="ThamizhiMorph", tier="anchor")], tier="anchor")
    return _Fake()


# --- decoder rules (pure, offline) ---

def test_bare_noun_is_pakapadam():
    f = decoder.decode_formation("மரம்", MorphAnalysis(lemma="மரம்", pos="noun", tags=["nom"]))
    assert f.word_type == "பகாப்பதம்"
    assert [c.part for c in f.components] == ["பகுதி"] and f.components[0].form == "மரம்"


def test_inflected_noun_full_decompose():
    f = decoder.decode_formation("மரத்தில்", MorphAnalysis(lemma="மரம்", pos="noun", tags=["infInc", "loc"]))
    assert f.word_type == "பகுபதம்"
    parts = {c.part: c.form for c in f.components}
    assert parts == {"பகுதி": "மரம்", "சாரியை": "அத்து", "விகுதி": "இல்"}
    assert any(s.type == "திரிதல்" and s.authority == "Tholkappiyam" for s in f.sandhi)
    assert all(c.authority == "Nannūl" for c in f.components)   # six-part labels are Nannūl's


def test_plural_noun_sandhi():
    f = decoder.decode_formation("மரங்கள்", MorphAnalysis(lemma="மரம்", pos="noun", tags=["pl", "nom"]))
    assert any(c.part == "விகுதி" and c.form == "கள்" for c in f.components)
    assert any(s.type == "திரிதல்" and "ங்" in s.detail for s in f.sandhi)


def test_dative_doubling():
    f = decoder.decode_formation("மரத்துக்கு", MorphAnalysis(lemma="மரம்", pos="noun", tags=["infInc", "dat"]))
    assert any(c.part == "விகுதி" and c.form == "கு" for c in f.components)
    assert any(s.type == "வல்லினம்மிகுதல்" for s in f.sandhi)


def test_verb_tense_and_ending():
    an = MorphAnalysis(lemma="வா", pos="verb", tags=["fin", "sim", "strong", "past=த்", "3sgm=ஆன்"])
    f = decoder.decode_formation("வந்தான்", an)
    assert f.word_type == "பகுபதம்"
    parts = {c.part: c.form for c in f.components}
    assert parts == {"பகுதி": "வா", "இடைநிலை": "த்", "விகுதி": "ஆன்"}
    tense, png = decoder.decode_verb_grammar(an)
    assert tense == "இறந்தகாலம்" and png == "படர்க்கை ஆண்பால் ஒருமை"


def test_borrowing_treated_as_pakapadam():
    f = decoder.decode_formation("புத்தகம்", MorphAnalysis(lemma="புத்தகம்", pos="noun", tags=["nom"]))
    assert f.word_type == "பகாப்பதம்"


# --- engine wiring ---

def test_engine_formation_decoded_no_gap():
    e = Engine(morph=_mk("மரத்தில்", [MorphAnalysis(lemma="மரம்", pos="noun", tags=["infInc", "loc"])]))
    a = asyncio.run(e.analyze("மரத்தில்", "மரத்தில்", include=["formation"]))
    assert a.formation.components and not any(g.field == "formation" for g in a.gaps)


def test_engine_grammar_gets_verb_tense():
    an = [MorphAnalysis(lemma="வா", pos="verb", tags=["fin", "past=த்", "3sgm=ஆன்"])]
    a = asyncio.run(Engine(morph=_mk("வந்தான்", an)).analyze("வந்தான்", "வந்தான்", include=["grammar"]))
    assert a.grammar.tense == "இறந்தகாலம்" and a.grammar.person_number_gender == "படர்க்கை ஆண்பால் ஒருமை"


def test_engine_no_fst_is_formation_gap():
    a = asyncio.run(Engine().analyze("மரம்", "மரம்", include=["formation"]))
    assert not a.formation.components and any(g.field == "formation" for g in a.gaps)


# --- tools ---

def test_eight_tools_registered():
    names = {t.name for t in asyncio.run(server.mcp.list_tools())}
    assert {"analyze_word", "suggest_native_equivalent", "classify_origin", "get_root",
            "get_meaning", "enrich_word", "explain_formation", "explain_grammar"} <= names


def test_explain_formation_tool(monkeypatch):
    monkeypatch.setattr(eng, "_default",
                        Engine(morph=_mk("மரத்தில்", [MorphAnalysis(lemma="மரம்", pos="noun", tags=["infInc", "loc"])])))
    out = json.loads(asyncio.run(server.explain_formation(server.ExplainFormationInput(word="மரத்தில்"))))
    assert out["formation"]["word_type"] == "பகுபதம்"
    forms = {c["part"]: c["form"] for c in out["formation"]["components"]}
    assert forms["பகுதி"] == "மரம்" and forms["விகுதி"] == "இல்"


def test_explain_grammar_tool(monkeypatch):
    an = [MorphAnalysis(lemma="வா", pos="verb", tags=["fin", "past=த்", "3sgm=ஆன்"])]
    monkeypatch.setattr(eng, "_default", Engine(morph=_mk("வந்தான்", an)))
    out = json.loads(asyncio.run(server.explain_grammar(server.ExplainGrammarInput(word="வந்தான்"))))
    assert out["grammar"]["word_class"] == "வினை" and out["grammar"]["tense"] == "இறந்தகாலம்"


def test_explain_tools_reject_non_tamil():
    assert asyncio.run(server.explain_formation(server.ExplainFormationInput(word="tree"))).startswith("Error:")
    assert asyncio.run(server.explain_grammar(server.ExplainGrammarInput(word="tree"))).startswith("Error:")


needs_fst = pytest.mark.skipif(not config.flookup_available(),
                               reason="flookup/FSTs not on this machine (see data/PINS.md)")


@needs_fst
def test_live_formation_marathil(monkeypatch):
    from thamizh_mcp.adapters.thamizhimorph import ThamizhiMorphAdapter
    monkeypatch.setattr(eng, "_default", Engine(morph=ThamizhiMorphAdapter()))
    out = json.loads(asyncio.run(server.explain_formation(server.ExplainFormationInput(word="மரத்தில்"))))
    forms = {c["part"]: c["form"] for c in out["formation"]["components"]}
    assert forms.get("பகுதி") == "மரம்" and "விகுதி" in forms
