"""THAMIZH MCP server — thin MCP head over the plain-Python engine (blueprint §8).

Keep this layer thin: tools validate input, call thamizh_mcp.core.engine, serialize output.
All linguistic logic lives in core/; other heads (FastAPI REST, CLI) reuse the same engine.
"""
from __future__ import annotations

import json
from typing import Optional

from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, ConfigDict, Field

from thamizh_mcp.core import engine
from thamizh_mcp.normalize import normalize

mcp = FastMCP("thamizh_mcp")

_SECTIONS = ("origin", "root", "meaning", "formation", "grammar", "native_equivalent")


class AnalyzeWordInput(BaseModel):
    """Input for analyze_word."""
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    word: str = Field(..., min_length=1, max_length=100,
                      description="One Tamil word in Tamil script, e.g. மரத்தில் or கம்ப்யூட்டர்.")
    include: Optional[list[str]] = Field(
        default=None,
        description=f"Sections to compute (default: all). Subset of {list(_SECTIONS)}.")
    allow_enrichment: bool = Field(
        default=True,
        description="Permit evolving-tier internet pulls (Tamil Wiktionary etc.) on anchor miss; "
                    "results are cached with provenance.")


@mcp.tool(
    name="analyze_word",
    annotations={
        "title": "Analyze a Tamil word (சொல் இலக்கணம்)",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def analyze_word(params: AnalyzeWordInput) -> str:
    """Full grounded analysis of one Tamil word: origin (இயற்சொல்/திரிசொல்/திசைச்சொல்/வடசொல்/loan),
    root+meaning, formation (பகுபத உறுப்பு, புணர்ச்சி), grammar (Tholkappiyam-first), and — only
    for non-native words — ATTESTED native Tamil equivalents.

    Every field carries provenance (source, tier, authority, retrieval date). Fields no source
    can ground are returned in `gaps` — never invented. Ambiguous morphology returns ALL analyses.

    Args:
        params: word (required, Tamil script), include (optional section filter),
                allow_enrichment (default true).

    Returns:
        str: JSON WordAnalysis object (see schemas/word_analysis_schema.json). SCAFFOLD STATUS:
        currently returns the schema-valid all-gaps object — grounding sources land in Phase 1/3.

    Error handling:
        Non-Tamil / multi-word / empty input returns "Error: ..." with what to fix.
    """
    try:
        normalized = normalize(params.word)
    except ValueError as exc:
        return f"Error: {exc}"
    include = params.include
    if include is not None:
        bad = sorted(set(include) - set(_SECTIONS))
        if bad:
            return f"Error: unknown include section(s) {bad}. Valid: {list(_SECTIONS)}."
    analysis = await engine.analyze_word(
        params.word, normalized, include=include, allow_enrichment=params.allow_enrichment
    )
    return analysis.to_json()


class SuggestNativeEquivalentInput(BaseModel):
    """Input for suggest_native_equivalent."""
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    word: str = Field(..., min_length=1, max_length=100,
                      description="One Tamil word in Tamil script, e.g. அகராதி or கம்ப்யூட்டர்.")
    allow_enrichment: bool = Field(
        default=True,
        description="Permit evolving-tier pulls on anchor miss; cached with provenance.")


@mcp.tool(
    name="suggest_native_equivalent",
    annotations={
        "title": "Suggest attested pure-Tamil equivalents (தனித்தமிழ்)",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def suggest_native_equivalent(params: SuggestNativeEquivalentInput) -> str:
    """ATTESTED pure-Tamil (தனித்தமிழ்) equivalents for a borrowed/Indic word — e.g. அகராதி →
    அகரமுதலி/அகரவரிசை. Grounded in named community glossaries (Indic-To-Pure-Tamil); every
    candidate carries its attestation source. An invented coinage never surfaces.

    A word with no attested equivalent (or a native word not in the lists) returns
    applicable=false with an honest gap — origin classification (Phase 2) will tighten this.

    Args:
        params: word (required, Tamil script), allow_enrichment (default true).

    Returns:
        str: JSON { word, normalized, native_equivalent{applicable, candidates[], note, sources[]},
        gaps[] }.

    Error handling:
        Non-Tamil / multi-word / empty input returns "Error: ..." with what to fix.
    """
    try:
        normalized = normalize(params.word)
    except ValueError as exc:
        return f"Error: {exc}"
    analysis = await engine.suggest_native_equivalent(
        params.word, normalized, allow_enrichment=params.allow_enrichment)
    out = {
        "word": analysis.word,
        "normalized": analysis.normalized,
        "native_equivalent": analysis.native_equivalent.model_dump(by_alias=True),
        "gaps": [g.model_dump() for g in analysis.gaps],
    }
    return json.dumps(out, ensure_ascii=False, indent=2)


class ClassifyOriginInput(BaseModel):
    """Input for classify_origin."""
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    word: str = Field(..., min_length=1, max_length=100,
                      description="One Tamil word in Tamil script, e.g. மரம் or யோகம் or ரயில்.")


@mcp.tool(
    name="classify_origin",
    annotations={
        "title": "Classify a Tamil word's origin (சொல் வகை)",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def classify_origin(params: ClassifyOriginInput) -> str:
    """Classify one Tamil word's origin — இயற்சொல் (native), வடசொல் (Sanskrit), or loanword —
    grounded in Tamil orthography (Grantha letters, Tholkappiyam முதல்/இறுதி எழுத்து rules), the
    native ThamizhiMorph FST parse, and I2PT borrowed-word attestation.

    HONEST BOUNDARY: திரிசொல் (literary) and திசைச்சொல் (regional) need lexical/dialectal corpus
    knowledge unavailable offline and are never guessed — when the signals can't ground a class,
    origin.class is "unknown" with an evidence note and a matching gap. Each claim carries its
    source; competing readings are kept in origin.alternatives.

    Args:
        params: word (required, Tamil script).

    Returns:
        str: JSON { word, normalized, origin{class, is_native, evidence, confidence,
        alternatives[], sources[]}, gaps[] }.

    Error handling:
        Non-Tamil / multi-word / empty input returns "Error: ..." with what to fix.
    """
    try:
        normalized = normalize(params.word)
    except ValueError as exc:
        return f"Error: {exc}"
    analysis = await engine.classify_origin(params.word, normalized)
    out = {
        "word": analysis.word,
        "normalized": analysis.normalized,
        "origin": analysis.origin.model_dump(by_alias=True),
        "gaps": [g.model_dump() for g in analysis.gaps],
    }
    return json.dumps(out, ensure_ascii=False, indent=2)


class GetRootInput(BaseModel):
    """Input for get_root."""
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    word: str = Field(..., min_length=1, max_length=100,
                      description="One Tamil word in Tamil script, e.g. மரத்தில் or வந்தான்.")


@mcp.tool(
    name="get_root",
    annotations={
        "title": "Find a Tamil word's root/lemma (அடிச்சொல்)",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def get_root(params: GetRootInput) -> str:
    """The root/lemma (அடிச்சொல்) and part of speech of an inflected Tamil word, from the
    ThamizhiMorph FST anchor — e.g. மரத்தில் → மரம். When morphology is ambiguous the lemma is
    left empty and ALL valid analyses are returned in all_analyses (never silently disambiguated);
    with no FST available the lemma is an honest gap, not a guess.

    Args:
        params: word (required, Tamil script).

    Returns:
        str: JSON { word, normalized, lemma, pos, all_analyses[{lemma, pos, tags}], gaps[] }.

    Error handling:
        Non-Tamil / multi-word / empty input returns "Error: ..." with what to fix.
    """
    try:
        normalized = normalize(params.word)
    except ValueError as exc:
        return f"Error: {exc}"
    analysis = await engine.get_root(params.word, normalized)
    out = {
        "word": analysis.word,
        "normalized": analysis.normalized,
        "lemma": analysis.lemma,
        "pos": analysis.pos,
        "all_analyses": [m.model_dump() for m in analysis.all_analyses],
        "gaps": [g.model_dump() for g in analysis.gaps],
    }
    return json.dumps(out, ensure_ascii=False, indent=2)


class GetMeaningInput(BaseModel):
    """Input for get_meaning."""
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    word: str = Field(..., min_length=1, max_length=100,
                      description="One Tamil word in Tamil script, e.g. புத்தகம் or மரம்.")
    allow_enrichment: bool = Field(
        default=True,
        description="Permit evolving-tier internet pulls (Tamil Wiktionary etc.) on anchor miss; "
                    "results are cached with provenance.")


@mcp.tool(
    name="get_meaning",
    annotations={
        "title": "Get a Tamil word's meaning (பொருள்)",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def get_meaning(params: GetMeaningInput) -> str:
    """The meaning (பொருள்) of a Tamil word — senses with provenance, served from the self-
    enriching store or pulled from an evolving source (Tamil Wiktionary) and cached. Each sense
    carries its source and retrieval date. A word no source can ground returns an honest gap with
    the reason, never an invented gloss.

    Args:
        params: word (required, Tamil script), allow_enrichment (default true).

    Returns:
        str: JSON { word, normalized, meaning{senses[], sources[]}, gaps[] }.

    Error handling:
        Non-Tamil / multi-word / empty input returns "Error: ..." with what to fix.
    """
    try:
        normalized = normalize(params.word)
    except ValueError as exc:
        return f"Error: {exc}"
    analysis = await engine.get_meaning(
        params.word, normalized, allow_enrichment=params.allow_enrichment)
    out = {
        "word": analysis.word,
        "normalized": analysis.normalized,
        "meaning": analysis.meaning.model_dump(by_alias=True),
        "gaps": [g.model_dump() for g in analysis.gaps],
    }
    return json.dumps(out, ensure_ascii=False, indent=2)


class EnrichWordInput(BaseModel):
    """Input for enrich_word."""
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    word: str = Field(..., min_length=1, max_length=100,
                      description="One Tamil word in Tamil script to enrich, e.g. புத்தகம்.")
    include: Optional[list[str]] = Field(
        default=None,
        description=f"Sections to enrich (default: all). Subset of {list(_SECTIONS)}.")


@mcp.tool(
    name="enrich_word",
    annotations={
        "title": "Enrich the store for a Tamil word (self-enriching cache)",
        "readOnlyHint": False,      # writes evolving claims to the knowledge store
        "destructiveHint": False,
        "idempotentHint": True,     # re-running re-serves the same cached claim, no duplicate pull
        "openWorldHint": True,
    },
)
async def enrich_word(params: EnrichWordInput) -> str:
    """Force the self-enriching loop for a word: pull from evolving sources (Tamil Wiktionary) on
    anchor miss and write the results back to the knowledge store with provenance, then report
    what the store now holds. Use it to pre-warm or grow the cache. Only fields with an evolving
    source land in the store (today: meaning); rule-based/anchor fields are not cached.

    Args:
        params: word (required, Tamil script), include (optional section filter).

    Returns:
        str: JSON { word, normalized, cached_claims[{field, source, tier, retrieved}], gaps[] }.

    Error handling:
        Non-Tamil / multi-word / empty input returns "Error: ..." with what to fix.
    """
    try:
        normalized = normalize(params.word)
    except ValueError as exc:
        return f"Error: {exc}"
    include = params.include
    if include is not None:
        bad = sorted(set(include) - set(_SECTIONS))
        if bad:
            return f"Error: unknown include section(s) {bad}. Valid: {list(_SECTIONS)}."
    analysis, cached = await engine.enrich_word(params.word, normalized, include=include)
    out = {
        "word": analysis.word,
        "normalized": analysis.normalized,
        "cached_claims": [
            {"field": c.field, "source": c.source, "tier": c.tier, "retrieved": c.retrieved}
            for c in cached
        ],
        "gaps": [g.model_dump() for g in analysis.gaps],
    }
    return json.dumps(out, ensure_ascii=False, indent=2)


class ExplainFormationInput(BaseModel):
    """Input for explain_formation."""
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    word: str = Field(..., min_length=1, max_length=100,
                      description="One Tamil word in Tamil script, e.g. மரத்தில் or வந்தான்.")


@mcp.tool(
    name="explain_formation",
    annotations={
        "title": "Explain a Tamil word's formation (பகுபத உறுப்பு)",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def explain_formation(params: ExplainFormationInput) -> str:
    """Decompose an inflected Tamil word into its பகுபத உறுப்பு (Nannūl's six parts —
    பகுதி/விகுதி/இடைநிலை/சாரியை/சந்தி/விகாரம்) with the புணர்ச்சி (sandhi) at each join, decoded from
    the ThamizhiMorph FST — e.g. மரத்தில் → பகுதி மரம் + சாரியை அத்து + விகுதி இல் (திரிதல்: ம்→த்).

    Grounds only what the FST provides: a simple/borrowed word is பகாப்பதம்; a join the FST does not
    determine is left unnamed, never invented. Component labels carry Nannūl authority; sandhi carries
    Tholkappiyam (எழுத்ததிகாரம், புணரியல்). No FST analysis → honest gap.

    Args:
        params: word (required, Tamil script).

    Returns:
        str: JSON { word, normalized, formation{word_type, components[{part, form, role, authority}],
        sandhi[{type, detail, authority}], sources[]}, gaps[] }.

    Error handling:
        Non-Tamil / multi-word / empty input returns "Error: ..." with what to fix.
    """
    try:
        normalized = normalize(params.word)
    except ValueError as exc:
        return f"Error: {exc}"
    analysis = await engine.explain_formation(params.word, normalized)
    out = {
        "word": analysis.word,
        "normalized": analysis.normalized,
        "formation": analysis.formation.model_dump(by_alias=True),
        "gaps": [g.model_dump() for g in analysis.gaps],
    }
    return json.dumps(out, ensure_ascii=False, indent=2)


class ExplainGrammarInput(BaseModel):
    """Input for explain_grammar."""
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    word: str = Field(..., min_length=1, max_length=100,
                      description="One Tamil word in Tamil script, e.g. மரத்தில் or வந்தான்.")


@mcp.tool(
    name="explain_grammar",
    annotations={
        "title": "Explain a Tamil word's grammar (சொல் இலக்கணம்)",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def explain_grammar(params: ExplainGrammarInput) -> str:
    """Grammatical analysis of one Tamil word — சொல் வகை (word class பெயர்/வினை/இடை/உரி), வேற்றுமை
    (case, for nouns), and tense + முற்று (person-number-gender, for verbs) — decoded from the
    ThamizhiMorph FST, Tholkappiyam-first with the authority recorded.

    Ambiguity is preserved: the இல் suffix reads as both 5th (ablative) and 7th (locative) case, so
    both are reported rather than guessed. Word class the FST cannot map → honest gap.

    Args:
        params: word (required, Tamil script).

    Returns:
        str: JSON { word, normalized, grammar{word_class, case{number, name, function}, tense,
        person_number_gender, authority, notes, sources[]}, gaps[] }.

    Error handling:
        Non-Tamil / multi-word / empty input returns "Error: ..." with what to fix.
    """
    try:
        normalized = normalize(params.word)
    except ValueError as exc:
        return f"Error: {exc}"
    analysis = await engine.explain_grammar(params.word, normalized)
    out = {
        "word": analysis.word,
        "normalized": analysis.normalized,
        "grammar": analysis.grammar.model_dump(by_alias=True),
        "gaps": [g.model_dump() for g in analysis.gaps],
    }
    return json.dumps(out, ensure_ascii=False, indent=2)


def main() -> None:
    """stdio transport (local v1); streamable HTTP arrives with the Cloud Run deploy (Phase 3+)."""
    mcp.run()


if __name__ == "__main__":
    main()
