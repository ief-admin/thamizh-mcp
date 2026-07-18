"""Pydantic contract for one Tamil word analysis.

Mirrors schemas/word_analysis_schema.json (the canonical contract from the blueprint, §3).
Contract deviations logged here per blueprint:
  - v0.1: `Grammar.word_class` gains "unknown" so a schema-valid all-gaps object can exist
    before sources are wired (gap is still recorded explicitly in `WordAnalysis.gaps`).

Non-negotiables encoded in this shape (blueprint §2):
  provenance on every field (SourceRef: tier + authority + retrieved), honest gaps (Gap),
  all ambiguous analyses kept (all_analyses / alternatives), attested-only equivalents
  (EquivalentCandidate requires `source` + `attestation`).
"""
from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

Tier = Literal["anchor", "evolving"]
Authority = Literal["Tholkappiyam", "Nannūl"]

OriginClass = Literal["இயற்சொல்", "திரிசொல்", "திசைச்சொல்", "வடசொல்", "loanword", "unknown"]
Pos = Literal["பெயர்ச்சொல்", "வினைச்சொல்", "இடைச்சொல்", "உரிச்சொல்", "unknown"]
WordClass = Literal["பெயர்", "வினை", "இடை", "உரிச்சொல்", "unknown"]
WordType = Literal["பகுபதம்", "பகாப்பதம்", "unknown"]
ComponentPart = Literal["பகுதி", "விகுதி", "இடைநிலை", "சாரியை", "சந்தி", "விகாரம்"]
SandhiType = Literal["தோன்றல்", "திரிதல்", "கெடுதல்", "வல்லினம்மிகுதல்", "வல்லினம்மிகாமை"]
Adaptation = Literal["தற்சமம்", "தற்பவம்"]
Register = Literal["technical", "literary", "everyday"]
Attestation = Literal["attested", "proposed"]


class SourceRef(BaseModel):
    """Provenance for one claim. Anchors pin a version; evolving pulls pin a retrieval date."""
    name: str
    tier: Optional[Tier] = None
    authority: Optional[Authority] = None
    ref: Optional[str] = None
    retrieved: Optional[str] = None


class Origin(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    class_: OriginClass = Field(default="unknown", alias="class")
    is_native: bool = False
    borrowed_from: Optional[str] = None
    adaptation: Optional[Adaptation] = None
    evidence: str = ""
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    alternatives: list[dict[str, Any]] = Field(default_factory=list)
    sources: list[SourceRef] = Field(default_factory=list)


class MorphAnalysis(BaseModel):
    """One of possibly several valid analyses — never silently disambiguate."""
    lemma: str
    pos: str
    tags: list[str] = Field(default_factory=list)


class Sense(BaseModel):
    gloss_ta: Optional[str] = None
    gloss_en: Optional[str] = None
    pos: Optional[str] = None
    citation: Optional[str] = None


class Meaning(BaseModel):
    senses: list[Sense] = Field(default_factory=list)
    sources: list[SourceRef] = Field(default_factory=list)


class FormationComponent(BaseModel):
    part: ComponentPart
    form: str
    role: Optional[str] = None
    authority: Optional[Authority] = None   # six-part labels: Nannūl; underlying elements: Tholkappiyam


class SandhiEvent(BaseModel):
    type: SandhiType
    detail: Optional[str] = None
    authority: Optional[Authority] = None   # புணர்ச்சி/விகாரம்: Tholkappiyam (எழுத்ததிகாரம், புணரியல்)


class Formation(BaseModel):
    word_type: WordType = "unknown"
    components: list[FormationComponent] = Field(default_factory=list)
    sandhi: list[SandhiEvent] = Field(default_factory=list)
    sources: list[SourceRef] = Field(default_factory=list)


class GrammarCase(BaseModel):
    number: int = Field(ge=1, le=8)
    name: Optional[str] = None      # e.g. ஏழாம் வேற்றுமை
    function: Optional[str] = None  # e.g. locative / இடப்பொருள்


class Grammar(BaseModel):
    word_class: WordClass = "unknown"
    case: Optional[GrammarCase] = None
    tense: Optional[str] = None
    person_number_gender: Optional[str] = None
    authority: Optional[Authority] = None
    notes: Optional[str] = None
    sources: list[SourceRef] = Field(default_factory=list)


class EquivalentCandidate(BaseModel):
    """Attested-only: `source` + `attestation` are REQUIRED. The merge layer drops any
    candidate lacking an attestation source — an invented coinage can never surface."""
    model_config = ConfigDict(populate_by_name=True)

    equivalent: str
    source: str
    tier: Optional[Tier] = None
    register_: Optional[Register] = Field(default=None, alias="register")
    attestation: Attestation
    confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    citation: Optional[str] = None


class NativeEquivalent(BaseModel):
    applicable: bool = False
    candidates: list[EquivalentCandidate] = Field(default_factory=list)
    note: Optional[str] = None
    sources: list[SourceRef] = Field(default_factory=list)


class Gap(BaseModel):
    """An explicit honest gap — a field no source could ground."""
    field: str
    note: str


class WordAnalysis(BaseModel):
    """The canonical word analysis object (blueprint §3)."""
    word: str
    normalized: str
    origin: Origin = Field(default_factory=Origin)
    lemma: str = ""
    all_analyses: list[MorphAnalysis] = Field(default_factory=list)
    pos: Pos = "unknown"
    meaning: Meaning = Field(default_factory=Meaning)
    formation: Formation = Field(default_factory=Formation)
    grammar: Grammar = Field(default_factory=Grammar)
    native_equivalent: NativeEquivalent = Field(default_factory=NativeEquivalent)
    gaps: list[Gap] = Field(default_factory=list)
    sources: list[SourceRef] = Field(default_factory=list)

    def to_json(self) -> str:
        return self.model_dump_json(by_alias=True, indent=2)


STUB_NOTE = "no grounding source wired yet (scaffold stub — Phase 1/3 pending)"


def empty_analysis(word: str, normalized: str) -> WordAnalysis:
    """Schema-valid, all-gaps analysis: every unfilled field is an explicit Gap, never a guess."""
    return WordAnalysis(
        word=word,
        normalized=normalized,
        origin=Origin(evidence=STUB_NOTE),
        native_equivalent=NativeEquivalent(
            applicable=False, note="origin unresolved — equivalent check not applicable yet"
        ),
        gaps=[
            Gap(field=f, note=STUB_NOTE)
            for f in ("origin", "lemma", "pos", "meaning", "formation", "grammar", "native_equivalent")
        ],
    )
