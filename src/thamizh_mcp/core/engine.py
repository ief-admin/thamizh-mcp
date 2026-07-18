"""Analysis core — the plain-Python engine every head (MCP/REST/CLI) sits on (blueprint §8).

Pipeline: morphology (stateless FST anchor) fills lemma/analyses/pos/grammar-case;
meaning follows the enrichment loop: store → evolving pull (if allowed) → write back.
Unfilled fields are explicit gaps — never guesses. Formation/origin/native-equivalent
decoding lands next (Phase 2/3).
"""
from __future__ import annotations

import datetime as _dt
from typing import Optional, Sequence

from thamizh_mcp import config
from thamizh_mcp.adapters.base import AdapterResult, SourceAdapter
from thamizh_mcp.core import classifier, decoder
from thamizh_mcp.schema import (
    STUB_NOTE, EquivalentCandidate, Gap, Grammar, Meaning, NativeEquivalent, Origin, Sense,
    SourceRef, WordAnalysis, empty_analysis,
)
from thamizh_mcp.store.knowledge import Claim, KnowledgeStore


class Engine:
    def __init__(
        self,
        morph: Optional[SourceAdapter] = None,
        meaning_sources: Sequence[SourceAdapter] = (),
        equivalent_sources: Sequence[SourceAdapter] = (),
        store: Optional[KnowledgeStore] = None,
    ):
        self.morph = morph
        self.meaning_sources = list(meaning_sources)
        self.equivalent_sources = list(equivalent_sources)
        self.store = store

    async def analyze(
        self, word: str, normalized: str,
        include: Optional[list[str]] = None, allow_enrichment: bool = True,
        force_refresh: bool = False,
    ) -> WordAnalysis:
        a = empty_analysis(word, normalized)
        a.gaps = []
        wants = set(include) if include else {"origin", "root", "meaning", "formation", "grammar", "native_equivalent"}

        morph_ran = bool({"root", "grammar", "formation"} & wants)
        if morph_ran:
            await self._fill_morphology(a, normalized, wants)

        # Origin is computed before native_equivalent so it can gate it (native word → no equivalent).
        origin = None
        if {"origin", "native_equivalent"} & wants:
            origin = await self._classify_origin(a, normalized, morph_ran)
            if "origin" in wants:
                a.origin = origin
                a.sources.extend(origin.sources)
                if origin.class_ == "unknown":
                    a.gaps.append(Gap(field="origin", note=origin.evidence))

        if "meaning" in wants:
            await self._fill_meaning(a, normalized, allow_enrichment, force_refresh)
        if "native_equivalent" in wants:
            await self._fill_native_equivalent(a, normalized, allow_enrichment, origin)
        if "formation" in wants:
            self._fill_formation(a, normalized)
        return a

    async def _fill_morphology(self, a: WordAnalysis, normalized: str, wants: set) -> None:
        if self.morph is None:
            for f in ("lemma", "pos", "grammar"):
                a.gaps.append(Gap(field=f, note=STUB_NOTE))
            return
        res = await self.morph.lookup(normalized)
        if not isinstance(res, AdapterResult):
            for f in ("lemma", "pos", "grammar"):
                a.gaps.append(Gap(field=f, note=f"{res.source}: {res.reason} — {res.note}"))
            return

        analyses = res.fields["all_analyses"]
        a.all_analyses = analyses
        a.sources.extend(res.sources)

        lemmas = {m.lemma for m in analyses}
        if len(lemmas) == 1:
            a.lemma = analyses[0].lemma
        else:
            a.gaps.append(Gap(field="lemma",
                              note=f"ambiguous — {len(lemmas)} candidate lemmas, see all_analyses"))

        pos_set = {decoder.map_pos(m.pos) for m in analyses}
        if len(pos_set) == 1 and "unknown" not in pos_set:
            a.pos = pos_set.pop()
        else:
            a.gaps.append(Gap(field="pos", note="ambiguous or unmapped POS across analyses"))

        if "grammar" in wants:
            grammar = Grammar(word_class=decoder.word_class_of(a.pos),
                              authority="Tholkappiyam",
                              sources=[*res.sources, decoder.THOLKAPPIYAM_COLLATIKARAM])
            cases = {(m2.number, m2.name, m2.function)
                     for m in analyses if (m2 := decoder.map_case(m.tags))}
            if len(cases) == 1:
                n, name, fn = cases.pop()
                grammar.case = decoder.GrammarCase(number=n, name=name, function=fn)
                grammar.sources.append(decoder.THOLKAPPIYAM_VETRUMAI)
            elif len(cases) > 1:
                grammar.notes = ("case ambiguous across analyses: "
                                 + "; ".join(sorted(c[1] for c in cases))
                                 + " — disambiguation is downstream (blueprint §2)")
                grammar.sources.append(decoder.THOLKAPPIYAM_VETRUMAI)
            # Verb முற்று: tense (காலம்) + person-number-gender, decoded from the FST's =forms.
            if a.pos == "வினைச்சொல்":
                verb_an = next((m for m in analyses if decoder.map_pos(m.pos) == "வினைச்சொல்"), None)
                if verb_an is not None:
                    grammar.tense, grammar.person_number_gender = decoder.decode_verb_grammar(verb_an)
                    if grammar.tense or grammar.person_number_gender:
                        grammar.sources.append(decoder.THOLKAPPIYAM_VINAIYIYAL)
            a.grammar = grammar
            if grammar.word_class == "unknown":
                a.gaps.append(Gap(field="grammar", note="word class unmapped — see all_analyses"))

    def _fill_formation(self, a: WordAnalysis, normalized: str) -> None:
        """Decode பகுபத உறுப்பு Formation from the FST analysis. No analysis → honest gap
        (never an invented split). When analyses share one lemma the decode is unambiguous; a
        structural split (different lemma/pos) is decoded from the primary with a note."""
        if not a.all_analyses:
            a.gaps.append(Gap(field="formation",
                              note="no FST analysis — formation cannot be decoded (no invented split)"))
            return
        a.formation = decoder.decode_formation(normalized, a.all_analyses[0])
        a.sources.extend(a.formation.sources)
        if len({m.lemma for m in a.all_analyses}) > 1:
            a.gaps.append(Gap(field="formation",
                              note="structural ambiguity — formation shown for the primary analysis; "
                                   "see all_analyses"))

    async def _fill_meaning(self, a: WordAnalysis, normalized: str, allow_enrichment: bool,
                            force_refresh: bool = False) -> None:
        # 1) cache — skipped on a forced refresh so evolving sources are re-pulled and overwritten
        if self.store is not None and not force_refresh:
            cached = await self.store.get_claims(normalized, "meaning")
            if cached:
                senses, srcs = [], []
                for c in cached:
                    senses.extend(Sense(**s) for s in c.value.get("senses", []))
                    srcs.append(SourceRef(name=c.source, tier=c.tier, retrieved=c.retrieved))
                a.meaning = Meaning(senses=senses, sources=srcs)
                a.sources.extend(srcs)
                return
        # 2) evolving pull (anchor meaning source — Madras Lexicon — pending, blueprint §10)
        misses: list[str] = []
        if allow_enrichment:
            for src in self.meaning_sources:
                res = await src.lookup(normalized)
                if isinstance(res, AdapterResult):
                    senses = [Sense(**s) for s in res.fields["senses"]]
                    a.meaning = Meaning(senses=senses, sources=res.sources)
                    a.sources.extend(res.sources)
                    # 3) write back — the store enriches itself with use
                    if self.store is not None:
                        ref = res.sources[0]
                        await self.store.put_claims(normalized, [Claim(
                            field="meaning", value=res.fields, source=ref.name, tier=res.tier,
                            retrieved=ref.retrieved or _dt.date.today().isoformat())])
                    return
                # honest miss: keep the WHY so the gap is diagnosable, not mysterious
                misses.append(f"{res.source}: {res.reason} — {res.note}")
        note = "no cached claim; anchor lexicon pending (blueprint §10)"
        if not allow_enrichment:
            note += "; enrichment disabled"
        elif misses:
            note += "; evolving pull failed → " + " | ".join(misses)
        else:
            note += "; no evolving source configured"
        a.gaps.append(Gap(field="meaning", note=note))

    async def _classify_origin(
        self, a: WordAnalysis, normalized: str, morph_ran: bool
    ) -> Origin:
        """Gather offline signals and classify origin (core/classifier.py holds the rules).

        FST native-parse signal: reuse the morphology run if it already happened; else query the
        FST directly. None means the FST is unavailable (no foma) — the native signal is absent,
        not False. I2PT membership is the borrowed-attestation signal.
        """
        if a.all_analyses:
            fst_native: Optional[bool] = True
        elif morph_ran:
            fst_native = False if self.morph is not None else None
        elif self.morph is not None:
            res = await self.morph.lookup(normalized)
            fst_native = isinstance(res, AdapterResult) and bool(res.fields.get("all_analyses"))
        else:
            fst_native = None
        in_i2pt = await self._word_in_i2pt(normalized)
        return classifier.classify_origin(normalized, fst_native_parse=fst_native, in_i2pt=in_i2pt)

    async def _word_in_i2pt(self, normalized: str) -> bool:
        """Is the word an attested borrowed headword in any configured equivalent source?"""
        for src in self.equivalent_sources:
            res = await src.lookup(normalized)
            if isinstance(res, AdapterResult) and res.fields.get("candidates"):
                return True
        return False

    async def _fill_native_equivalent(
        self, a: WordAnalysis, normalized: str, allow_enrichment: bool,
        origin: Optional[Origin] = None,
    ) -> None:
        """Surface ATTESTED pure-Tamil equivalents — gated on origin.

        A word classified native (இயற்சொல்) needs no equivalent: applicable=False, and NOT a gap
        (that is a resolved answer, not an unknown). Otherwise (borrowed, or origin undetermined)
        we look for attested equivalents; a miss is an honest gap. Network equivalent sources
        (future ta.wiktionary synonym mining) must honor allow_enrichment; the local I2PT CSVs do
        not touch the network, so they always run.
        """
        if origin is not None and origin.is_native:
            a.native_equivalent = NativeEquivalent(
                applicable=False,
                note=f"word classified native ({origin.class_}) — no borrowed equivalent applies")
            return
        misses: list[str] = []
        for src in self.equivalent_sources:
            res = await src.lookup(normalized)
            if isinstance(res, AdapterResult):
                candidates = [EquivalentCandidate(**c) for c in res.fields["candidates"]]
                if candidates:
                    cls = origin.class_ if origin is not None else "unknown"
                    a.native_equivalent = NativeEquivalent(
                        applicable=True, candidates=candidates, sources=res.sources,
                        note=f"attested pure-Tamil equivalents for a borrowed word (origin: {cls})")
                    a.sources.extend(res.sources)
                    return
            else:
                misses.append(f"{res.source}: {res.reason} — {res.note}")
        note = "no attested native equivalent found"
        if misses:
            note += " (" + " | ".join(misses) + ")"
        elif not self.equivalent_sources:
            note += "; no equivalent source configured"
        if origin is not None and origin.class_ == "unknown":
            note += "; origin undetermined"
        a.native_equivalent = NativeEquivalent(applicable=False, note=note)
        a.gaps.append(Gap(field="native_equivalent", note=note))

    async def enrich(
        self, word: str, normalized: str, include: Optional[list[str]] = None,
    ) -> tuple[WordAnalysis, list[Claim]]:
        """Force the self-enriching loop for a word (pull evolving sources, write back), then
        report what the knowledge store now holds. Unlike analyze, this is a WRITE: it exists to
        pre-warm / grow the cache. Only fields with an evolving source + write-back land in the
        store (today: meaning); rule-based and anchor fields (origin, morphology) are not cached.
        """
        a = await self.analyze(word, normalized, include=include, allow_enrichment=True)
        cached = await self.store.get_claims(normalized) if self.store is not None else []
        return a, cached

    async def refresh(
        self, words: Optional[Sequence[str]] = None, *, include: Optional[list[str]] = None,
        stale_days: Optional[int] = None, limit: int = 50,
    ) -> list[dict]:
        """Batch coverage-growth: force a fresh evolving pull (overwriting the cache) for the given
        words and/or store words whose evolving claim is older than `stale_days`. Sequential and
        capped at `limit` real refreshes to bound network cost. Returns a per-word report."""
        from thamizh_mcp.normalize import normalize
        include = include or ["meaning"]  # meaning is the only write-back field today
        targets = list(words or [])
        if stale_days is not None and self.store is not None:
            targets += await self.store.stale_words(stale_days)
        reports: list[dict] = []
        seen: set[str] = set()
        done = 0
        for raw in targets:
            if done >= limit:
                break
            try:
                normalized = normalize(raw)
            except ValueError as exc:
                reports.append({"word": raw, "error": str(exc)})
                continue
            if normalized in seen:
                continue
            seen.add(normalized)
            a = await self.analyze(raw, normalized, include=include,
                                   allow_enrichment=True, force_refresh=True)
            claims = await self.store.get_claims(normalized) if self.store is not None else []
            reports.append({
                "word": raw, "normalized": normalized,
                "refreshed": [{"field": c.field, "source": c.source, "tier": c.tier,
                               "retrieved": c.retrieved} for c in claims],
                "gaps": [g.field for g in a.gaps],
            })
            done += 1
        return reports


_default: Optional[Engine] = None


def default_engine() -> Engine:
    """Auto-wire from environment: FST anchor if available; Wiktionary + store for meaning."""
    global _default
    if _default is None:
        from thamizh_mcp.adapters.equivalents import IndicToPureTamilAdapter
        from thamizh_mcp.adapters.thamizhimorph import ThamizhiMorphAdapter
        from thamizh_mcp.adapters.wiktionary import TamilWiktionaryAdapter
        _default = Engine(
            morph=ThamizhiMorphAdapter() if config.flookup_available() else None,
            meaning_sources=[TamilWiktionaryAdapter()],
            equivalent_sources=[IndicToPureTamilAdapter()],
            store=KnowledgeStore(config.DEFAULT_DB),
        )
    return _default


async def analyze_word(
    word: str, normalized: str,
    include: Optional[list[str]] = None, allow_enrichment: bool = True,
) -> WordAnalysis:
    """Module-level entry point used by the MCP head (server.py)."""
    return await default_engine().analyze(word, normalized, include=include,
                                          allow_enrichment=allow_enrichment)


async def suggest_native_equivalent(
    word: str, normalized: str, allow_enrichment: bool = True,
) -> WordAnalysis:
    """Focused entry point for the suggest_native_equivalent MCP tool: only the equivalent
    section is computed (the full analysis is skipped). Returns the WordAnalysis so the head
    can serialize native_equivalent plus its honest gap when nothing is attested."""
    return await default_engine().analyze(word, normalized, include=["native_equivalent"],
                                          allow_enrichment=allow_enrichment)


async def classify_origin(word: str, normalized: str) -> WordAnalysis:
    """Focused entry point for the classify_origin MCP tool: computes only the origin section
    (இயற்சொல்/வடசொல்/loanword, or honest unknown). Returns the WordAnalysis so the head can
    serialize origin plus its honest gap when no signal grounds a class."""
    return await default_engine().analyze(word, normalized, include=["origin"])


async def get_root(word: str, normalized: str) -> WordAnalysis:
    """Focused entry point for the get_root MCP tool: runs only the morphology anchor and
    returns lemma + POS + every valid analysis. Ambiguous morphology leaves lemma empty and
    records the candidates in all_analyses — never silently disambiguated."""
    return await default_engine().analyze(word, normalized, include=["root"])


async def get_meaning(word: str, normalized: str, allow_enrichment: bool = True) -> WordAnalysis:
    """Focused entry point for the get_meaning MCP tool: runs only the meaning enrichment loop
    (store → evolving pull → write-back). Returns the WordAnalysis so the head can serialize the
    senses with provenance, or an honest gap when no source can ground a meaning."""
    return await default_engine().analyze(word, normalized, include=["meaning"],
                                          allow_enrichment=allow_enrichment)


async def enrich_word(
    word: str, normalized: str, include: Optional[list[str]] = None,
) -> tuple[WordAnalysis, list[Claim]]:
    """Entry point for the enrich_word MCP tool: forces the enrichment loop and returns the
    analysis plus the store's claims for the word so the head can report what is now cached."""
    return await default_engine().enrich(word, normalized, include=include)


async def refresh_sources(
    words: Optional[Sequence[str]] = None, *, include: Optional[list[str]] = None,
    stale_days: Optional[int] = None, limit: int = 50,
) -> list[dict]:
    """Entry point for the refresh_sources MCP tool: batch force-refresh of evolving claims."""
    return await default_engine().refresh(words, include=include, stale_days=stale_days, limit=limit)


async def explain_formation(word: str, normalized: str) -> WordAnalysis:
    """Focused entry point for the explain_formation MCP tool: decodes only the பகுபத உறுப்பு
    Formation (Nannūl six-part labels + Tholkappiyam sandhi) from the FST analysis."""
    return await default_engine().analyze(word, normalized, include=["formation"])


async def explain_grammar(word: str, normalized: str) -> WordAnalysis:
    """Focused entry point for the explain_grammar MCP tool: word class + வேற்றுமை + verb
    tense/முற்று, Tholkappiyam-first with authority recorded."""
    return await default_engine().analyze(word, normalized, include=["grammar"])
