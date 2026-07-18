"""A bare engine (no sources wired) must stay schema-valid and honest: source-dependent fields
are gaps, while rule-based origin (orthography/phonotactics) may resolve without any adapter."""
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pytest

from thamizh_mcp.core.engine import Engine
from thamizh_mcp.normalize import normalize
from thamizh_mcp.schema import WordAnalysis

FIXTURES = json.loads((Path(__file__).parent / "fixtures" / "words.json").read_text("utf-8"))
WORDS = [w["word"] for w in FIXTURES["words"]]


def run_bare(word: str) -> WordAnalysis:
    return asyncio.run(Engine().analyze(word, normalize(word)))


@pytest.mark.parametrize("word", WORDS)
def test_bare_engine_is_schema_valid_and_all_gaps(word):
    a = run_bare(word)
    revalidated = WordAnalysis.model_validate(json.loads(a.to_json()))
    assert revalidated.word == word and revalidated.normalized == normalize(word)
    gap_fields = {g.field for g in a.gaps}
    # source-dependent fields always gap without adapters
    assert {"lemma", "pos", "meaning", "grammar", "native_equivalent", "formation"} <= gap_fields
    assert a.lemma == "" and a.meaning.senses == []
    # origin is rule-based: it resolves from orthography (e.g. Grantha → வடசொல்) even with no sources;
    # only when no rule fires is it an honest gap.
    if a.origin.class_ == "unknown":
        assert "origin" in gap_fields
    else:
        assert "origin" not in gap_fields
    assert a.native_equivalent.applicable is False and a.native_equivalent.candidates == []


def test_include_filter_limits_sections():
    a = asyncio.run(Engine().analyze("மரம்", "மரம்", include=["meaning"]))
    assert {g.field for g in a.gaps} == {"meaning"}


def test_normalize_rejects_bad_input():
    for bad in ["", "   ", "tree", "மரம் வீடு", "மரம்123"]:
        with pytest.raises(ValueError):
            normalize(bad)


def test_normalize_nfc_and_joiners():
    assert normalize(" மரம்‌ ") == "மரம்"
