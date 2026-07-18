"""Origin classifier (objective 1): orthographic + phonotactic rules and signal fusion.

The rule logic is pure and offline — signals (FST parse, I2PT membership) are passed in directly,
so these run without foma. One live end-to-end test (needs_fst) exercises the real FST path.
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pytest

from thamizh_mcp import config
from thamizh_mcp.core import classifier
from thamizh_mcp.core.classifier import classify_origin, forbidden_final, forbidden_initial, grantha_letters_in
from thamizh_mcp.core.engine import Engine


# --- orthographic / phonotactic helpers ---

def test_grantha_detection():
    assert grantha_letters_in("ஜோதி") == ["ஜ"]
    assert grantha_letters_in("பாஷை") == ["ஷ"]
    assert grantha_letters_in("மரம்") == []


def test_forbidden_initial_rule():
    assert forbidden_initial("ரயில்") == "ர்"   # ர cannot begin a native word
    assert forbidden_initial("லாரி") == "ல்"
    assert forbidden_initial("மரம்") is None      # ம is a valid initial
    assert forbidden_initial("அகராதி") is None    # vowels always valid


def test_forbidden_final_rule():
    assert forbidden_final("கேக்") == "க்"        # bare vallinam final (cake)
    assert forbidden_final("மரம்") is None         # ம் is a permitted final
    assert forbidden_final("பணம்") is None


# --- classification decisions (signals injected) ---

def test_grantha_word_is_vadasol():
    o = classify_origin("ஜோதி", fst_native_parse=None, in_i2pt=False)  # ஜ is a Grantha letter
    assert o.class_ == "வடசொல்" and o.is_native is False and o.borrowed_from == "Sanskrit"
    assert any("Grantha" in (s.ref or "") or "எழுத்து" in (s.ref or "") for s in o.sources)


def test_forbidden_initial_is_loanword():
    o = classify_origin("ரயில்", fst_native_parse=None, in_i2pt=False)
    assert o.class_ == "loanword" and o.is_native is False
    assert "முதல் எழுத்து" in o.evidence


def test_forbidden_final_is_loanword():
    o = classify_origin("கேக்", fst_native_parse=None, in_i2pt=False)
    assert o.class_ == "loanword" and "இறுதி எழுத்து" in o.evidence


def test_i2pt_borrowed_without_marker_is_honest_unknown():
    # காபி (coffee): phonotactically native-looking, but attested as borrowed → don't guess the language.
    o = classify_origin("காபி", fst_native_parse=None, in_i2pt=True)
    assert o.class_ == "unknown" and o.is_native is False
    assert {alt["class"] for alt in o.alternatives} == {"வடசொல்", "loanword"}


def test_native_fst_parse_is_iyarcol():
    o = classify_origin("மரம்", fst_native_parse=True, in_i2pt=False)
    assert o.class_ == "இயற்சொல்" and o.is_native is True
    assert 0.0 < o.confidence < 1.0                       # moderate — naturalized borrowings can look native


def test_no_signal_is_unknown_not_a_guess():
    o = classify_origin("மரம்", fst_native_parse=False, in_i2pt=False)
    assert o.class_ == "unknown" and o.confidence == 0.0
    o2 = classify_origin("மரம்", fst_native_parse=None, in_i2pt=False)
    assert o2.class_ == "unknown" and "foma" in o2.evidence   # FST-unavailable reason surfaced


# --- engine wiring: origin gates native_equivalent ---

class _FakeMorph:
    name, tier = "ThamizhiMorph", "anchor"
    async def lookup(self, w):
        from thamizh_mcp.adapters.base import AdapterResult
        from thamizh_mcp.schema import MorphAnalysis, SourceRef
        return AdapterResult(fields={"all_analyses": [MorphAnalysis(lemma=w, pos="noun", tags=[])]},
                             sources=[SourceRef(name="ThamizhiMorph", tier="anchor")], tier="anchor")


def test_engine_native_word_gates_equivalent_off():
    a = asyncio.run(Engine(morph=_FakeMorph()).analyze("மரம்", "மரம்"))
    assert a.origin.class_ == "இயற்சொல்"
    assert a.native_equivalent.applicable is False
    assert not any(g.field == "native_equivalent" for g in a.gaps)  # native = resolved, not a gap


def test_engine_grantha_word_is_vadasol():
    a = asyncio.run(Engine(morph=_FakeMorph()).analyze("ஜோதி", "ஜோதி", include=["origin"]))
    assert a.origin.class_ == "வடசொல்"
    assert not any(g.field == "origin" for g in a.gaps)


needs_fst = pytest.mark.skipif(not config.flookup_available(),
                               reason="flookup/FSTs not on this machine (see data/PINS.md)")


@needs_fst
def test_live_native_word_is_iyarcol():
    from thamizh_mcp.adapters.thamizhimorph import ThamizhiMorphAdapter
    a = asyncio.run(Engine(morph=ThamizhiMorphAdapter()).analyze("மரம்", "மரம்", include=["origin"]))
    assert a.origin.class_ == "இயற்சொல்" and a.origin.is_native is True
