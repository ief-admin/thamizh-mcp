"""Linguistic decoding — lives in code, tested once, never re-derived by the model.

Implemented: FST POS tag → சொல் வகை (Tholkappiyam Collatikāram word classes);
FST case tag → வேற்றுமை (Tholkappiyam வேற்றுமையியல், eight cases);
FST tags → பகுபத உறுப்பு Formation (Nannūl six-part labels) + verb tense/PNG grammar.

Formation honesty boundary (blueprint §2, tamil-grammar.md §3): decode only what the FST grounds.
Verbs hand over surface forms (past=த், 3sgm=ஆன்) → பகுதி/இடைநிலை/விகுதி are read directly. Nouns give
feature tags (infInc, loc) → விகுதி is the case உருபு matched against the surface; சாரியை/விகாரம் are
asserted ONLY where a confident classical rule applies (e.g. -அம் noun → அத்து சாரியை, ம்→த் திரிதல்).
A join we cannot classify is left unnamed, never invented.
"""
from __future__ import annotations

from typing import Optional

from thamizh_mcp.schema import (
    Formation, FormationComponent, GrammarCase, MorphAnalysis, Pos, SandhiEvent, SourceRef,
    WordClass, WordType,
)

THOLKAPPIYAM_COLLATIKARAM = SourceRef(
    name="Tholkappiyam", tier="anchor", authority="Tholkappiyam",
    ref="சொல்லதிகாரம் — word classes பெயர்/வினை/இடை/உரி", retrieved="classical (edition-pinned in Phase 4)")
THOLKAPPIYAM_VETRUMAI = SourceRef(
    name="Tholkappiyam", tier="anchor", authority="Tholkappiyam",
    ref="சொல்லதிகாரம், வேற்றுமையியல் — the eight வேற்றுமை", retrieved="classical (edition-pinned in Phase 4)")
NANNOOL_PAKUPADAM = SourceRef(
    name="Nannūl", tier="anchor", authority="Nannūl",
    ref="பகுபத உறுப்பிலக்கணம் — the six உறுப்பு labels", retrieved="classical (edition-pinned in Phase 4)")
THOLKAPPIYAM_PUNARIYAL = SourceRef(
    name="Tholkappiyam", tier="anchor", authority="Tholkappiyam",
    ref="எழுத்ததிகாரம், புணரியல் — சந்தி/விகாரம்", retrieved="classical (edition-pinned in Phase 4)")
THOLKAPPIYAM_VINAIYIYAL = SourceRef(
    name="Tholkappiyam", tier="anchor", authority="Tholkappiyam",
    ref="சொல்லதிகாரம், வினையியல் — காலம்/முற்று", retrieved="classical (edition-pinned in Phase 4)")

# ThamizhiMorph POS tag → schema Pos (Tholkappiyam's four-way word-class frame).
_POS_MAP: dict[str, Pos] = {
    "noun": "பெயர்ச்சொல்", "propn": "பெயர்ச்சொல்", "pronoun": "பெயர்ச்சொல்", "pron": "பெயர்ச்சொல்",
    "verb": "வினைச்சொல்", "vb": "வினைச்சொல்",
    "part": "இடைச்சொல்", "particle": "இடைச்சொல்", "postp": "இடைச்சொல்",
    "adj": "உரிச்சொல்", "adv": "உரிச்சொல்",
}
_WORD_CLASS: dict[Pos, WordClass] = {
    "பெயர்ச்சொல்": "பெயர்", "வினைச்சொல்": "வினை", "இடைச்சொல்": "இடை", "உரிச்சொல்": "உரிச்சொல்",
}

# FST case tag → (number, name, function). Eight வேற்றுமை per Tholkappiyam;
# sociative ஒடு/உடன் sits inside the third case.
_CASE_MAP: dict[str, tuple[int, str, str]] = {
    "nom": (1, "முதல் வேற்றுமை (எழுவாய்)", "subject"),
    "acc": (2, "இரண்டாம் வேற்றுமை (ஐ)", "direct object"),
    "inst": (3, "மூன்றாம் வேற்றுமை (ஆல்)", "instrument/agency"),
    "soc": (3, "மூன்றாம் வேற்றுமை (ஒடு/உடன்)", "sociative/accompaniment"),
    "dat": (4, "நான்காம் வேற்றுமை (கு)", "dative/recipient"),
    "abl": (5, "ஐந்தாம் வேற்றுமை (இன்/இலிருந்து)", "ablative/comparison"),
    "gen": (6, "ஆறாம் வேற்றுமை (அது/உடைய)", "genitive/possession"),
    "loc": (7, "ஏழாம் வேற்றுமை (கண்/இல்)", "locative/இடப்பொருள்"),
    "voc": (8, "எட்டாம் வேற்றுமை (விளி)", "vocative/address"),
}


def map_pos(fst_pos_tag: str) -> Pos:
    return _POS_MAP.get(fst_pos_tag.lower(), "unknown")


def word_class_of(pos: Pos) -> WordClass:
    return _WORD_CLASS.get(pos, "unknown")


def map_case(tags: list[str]) -> Optional[GrammarCase]:
    """First recognized case tag → GrammarCase; None when no case tag present."""
    for t in tags:
        hit = _CASE_MAP.get(t.lower())
        if hit:
            return GrammarCase(number=hit[0], name=hit[1], function=hit[2])
    return None


# --- Formation / grammar decoding (Nannūl six-part உறுப்பு + Tholkappiyam elements) ---

# Verb tense marker (இடைநிலை): FST hands over the surface form (past=த்); we add the காலம் role.
_TENSE_ROLE: dict[str, str] = {
    "past": "இறந்தகாலம்", "pres": "நிகழ்காலம்", "fut": "எதிர்காலம்",
}
# Verb terminal ending (விகுதி): PNG code → முற்று role (person·gender·number).
_PNG_ROLE: dict[str, str] = {
    "1sg": "தன்மை ஒருமை", "2sg": "முன்னிலை ஒருமை",
    "3sgm": "படர்க்கை ஆண்பால் ஒருமை", "3sgf": "படர்க்கை பெண்பால் ஒருமை",
    "3sgn": "படர்க்கை ஒன்றன்பால் ஒருமை",
    "1pl": "தன்மை பன்மை", "2pl": "முன்னிலை பன்மை",
    "3pl": "படர்க்கை பலர்பால்", "3ple": "படர்க்கை பலர்பால்",
    "3sgh": "படர்க்கை உயர்திணை ஒருமை (மரியாதை)", "3sghe": "படர்க்கை உயர்திணை (மரியாதை)",
    "3plh": "படர்க்கை உயர்திணை பன்மை",
}
# Noun case tag → canonical உருபு form (the விகுதி). Surface-matched, so an ambiguous case
# (loc|soc both surface as இல்) yields the actual suffix; the case *function* stays in grammar.case.
_CASE_URUBU: dict[str, str] = {
    "acc": "ஐ", "inst": "ஆல்", "soc": "ஒடு", "dat": "கு", "abl": "இன்", "gen": "அது", "loc": "இல்",
}
_PULLI = "்"


def _split_tags(tags: list[str]) -> tuple[list[str], dict[str, str]]:
    """Split FST tags into bare tags and feature=form pairs ('past=த்' → {'past': 'த்'})."""
    bare: list[str] = []
    feats: dict[str, str] = {}
    for t in tags:
        if "=" in t:
            name, form = t.split("=", 1)
            feats[name] = form
        else:
            bare.append(t)
    return bare, feats


def _is_verb(pos: str) -> bool:
    return pos.lower() in ("verb", "vb")


def decode_verb_grammar(analysis: MorphAnalysis) -> tuple[Optional[str], Optional[str]]:
    """Verb காலம் (tense) and முற்று (person-number-gender) roles for grammar, or (None, None)."""
    if not _is_verb(analysis.pos):
        return None, None
    _, feats = _split_tags(analysis.tags)
    tense = next((_TENSE_ROLE[k] for k in _TENSE_ROLE if feats.get(k) not in (None, "", "∅")), None)
    png = next((_PNG_ROLE[k] for k in _PNG_ROLE if feats.get(k) not in (None, "", "∅")), None)
    return tense, png


def _am_stem(lemma: str) -> Optional[str]:
    """Oblique stem of an -அம் noun (மரம் → மர), or None if not an -அம் noun."""
    return lemma[:-2] if lemma.endswith("ம" + _PULLI) else None


def _decode_noun(lemma: str, word: str, bare: list[str],
                 comps: list[FormationComponent], sandhi: list[SandhiEvent]) -> bool:
    """Fill noun/pronoun உறுப்புகள். Returns whether the word is inflected."""
    inflected = False
    stem = _am_stem(lemma)
    # சாரியை — the oblique increment. Confident only for the -அம் declension (மரம் → மரத்து).
    if "infInc" in bare and stem is not None:
        inflected = True
        comps.append(FormationComponent(
            part="சாரியை", form="அத்து", role="oblique increment (சாரியை)", authority="Nannūl"))
        sandhi.append(SandhiEvent(
            type="திரிதல்", detail=f"{lemma} → {stem}த் — ம் changes to த் before the சாரியை",
            authority="Tholkappiyam"))
    # விகுதி — plural கள் and/or the case உருபு.
    if "pl" in bare:
        inflected = True
        if stem is not None:
            sandhi.append(SandhiEvent(
                type="திரிதல்", detail=f"{lemma} → {stem}ங் before the பன்மை விகுதி கள்",
                authority="Tholkappiyam"))
        comps.append(FormationComponent(
            part="விகுதி", form="கள்", role="பன்மை விகுதி (plural)", authority="Nannūl"))
    case_tags = [t for t in bare if t in _CASE_MAP and t != "nom"]
    urubu = _select_urubu(word, case_tags)
    if urubu is not None:
        inflected = True
        names = list(dict.fromkeys(_CASE_MAP[t][1] for t in case_tags))
        comps.append(FormationComponent(
            part="விகுதி", form=urubu, role=(" / ".join(names) + " உருபு"), authority="Nannūl"))
        if urubu == "கு" and "க்கு" in word:
            sandhi.append(SandhiEvent(
                type="வல்லினம்மிகுதல்", detail="க் doubles at the dative join (க்கு)",
                authority="Tholkappiyam"))
    return inflected


def _select_urubu(word: str, case_tags: list[str]) -> Optional[str]:
    """Pick the case உருபு that the surface actually ends with (longest match); fall back to the
    first tagged case's canonical form so an attested case still surfaces its suffix."""
    forms = [_CASE_URUBU[c] for c in case_tags if c in _CASE_URUBU]
    if not forms:
        return None
    matched = [f for f in forms if word.endswith(f)]
    return max(matched, key=len) if matched else forms[0]


def decode_formation(word: str, analysis: MorphAnalysis) -> Formation:
    """Decode one FST analysis into a பகுபத உறுப்பு Formation. Grounds only what the FST provides;
    unclassifiable joins are left unnamed (no invented split)."""
    lemma, pos = analysis.lemma, analysis.pos
    bare, feats = _split_tags(analysis.tags)
    comps: list[FormationComponent] = [FormationComponent(
        part="பகுதி", form=lemma, role="root/base (அடிச்சொல்)", authority="Nannūl")]
    sandhi: list[SandhiEvent] = []
    inflected = False

    if _is_verb(pos):
        for tcode, trole in _TENSE_ROLE.items():
            if feats.get(tcode) not in (None, "", "∅"):
                inflected = True
                comps.append(FormationComponent(
                    part="இடைநிலை", form=feats[tcode], role=trole, authority="Nannūl"))
                break
        for pcode, prole in _PNG_ROLE.items():
            if feats.get(pcode) not in (None, "", "∅"):
                inflected = True
                comps.append(FormationComponent(
                    part="விகுதி", form=feats[pcode], role=prole, authority="Nannūl"))
                break
    else:
        inflected = _decode_noun(lemma, word, bare, comps, sandhi)

    word_type: WordType = "பகுபதம்" if (inflected or word != lemma) else "பகாப்பதம்"
    sources = [NANNOOL_PAKUPADAM, THOLKAPPIYAM_PUNARIYAL]
    if _is_verb(pos):
        sources.append(THOLKAPPIYAM_VINAIYIYAL)
    elif any(c.part == "விகுதி" for c in comps):
        sources.append(THOLKAPPIYAM_VETRUMAI)
    return Formation(word_type=word_type, components=comps, sandhi=sandhi, sources=sources)
