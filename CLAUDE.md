# CLAUDE.md — Thamizh MCP (developer context for Claude Code)

Thamizh MCP is a Model Context Protocol server for Tamil word-grammar
(சொல் இலக்கணம்) analysis. It grounds every answer in authentic Tamil sources
(Tholkappiyam-first) and self-enriches from evolving internet Tamil data instead
of a hand-maintained dictionary. Public repo: github.com/ief-admin/thamizh-mcp
(Apache-2.0, nonprofit org IEF).

## Machine roles
- **minnaham (this Ubuntu box)** = build + live-test home. Real `foma` on PATH,
  open network (ta.wiktionary / dsal / tamilvu reachable), repo cloned on `develop`.
  All test runs, live enrichment pulls, and git happen here.
- **Windows / Cowork** = design + docs home (blueprint, memory, planning). Its
  sandbox blocks the Tamil sources and its E:\ mount corrupts git — never build there.

## Git identity — use everywhere, no exceptions
Commit as **Saran Saravanan <saravanan3@duck.com>**, GitHub **ssaravanan3**.
`git config --global` is already set to this on this box. NEVER commit under the
legacy `asaravanan75@gmail.com` / `asaravanan75-eng`. Verify: `git log --format='%an <%ae>' -1`.

## Branch workflow
`main` = stable, **protected** (PR-only, no force-push, no delete). `develop` =
integration. Loop: work on `develop` here → push → open PR `develop → main` at
milestones. After any history rewrite, other clones must `git reset --hard origin/main`
(not merge/rebase).

## Current state (2026-07-17)
**Phase 1 core DONE.** FastMCP server with `analyze_word` end-to-end: ThamizhiMorph
FST anchor (foma), SQLite per-claim knowledge store + self-enriching
pull→write-back→cache loop, Wiktionary adapter (descriptive UA + real ta.wiktionary
template-style parser).
**Native equivalents live (2026-07-17):** `IndicToPureTamilAdapter` over the vendored I2PT
sub-lists (per-candidate attestation, attested-only), wired into the engine
(`_fill_native_equivalent`) and exposed as the `suggest_native_equivalent` MCP tool.
**Origin classifier live (2026-07-17):** `core/classifier.py` — rule-based, Tholkappiyam-grounded
(Grantha letters via open-tamil; முதல்/இறுதி எழுத்து phonotactics) fused with the FST native-parse
and I2PT attestation. Classes இயற்சொல்/வடசொல்/loanword; honest `unknown` for திரிசொல்/திசைச்சொல் and
language-undetermined borrowings (never guessed). Exposed as `classify_origin`; origin now gates
`native_equivalent` (native word → not applicable).
**Root + meaning + enrich tools live (2026-07-17):** thin `get_root` (FST lemma/POS, keeps all
analyses), `get_meaning` (self-enriching store → Wiktionary pull, provenance-tagged), and
`enrich_word` (forces the pull→write-back loop, reports what the store now caches; the one
non-readOnly tool) MCP heads over the existing engine paths.
**Formation decoder live (2026-07-18):** `core/decoder.py` `decode_formation` — FST tags →
பகுபத உறுப்பு (Nannūl six parts) + Tholkappiyam சந்தி. Verbs read பகுதி/இடைநிலை/விகுதி straight from
the FST `=forms`; nouns get சாரியை/உருபு surface-grounded; joins classified only where a confident
classical rule applies (no invented split). Grammar now also carries verb tense + முற்று. Exposed as
`explain_formation` and `explain_grammar`.
**refresh_sources live (2026-07-18):** batch coverage-growth tool — force-refreshes evolving claims
(explicit `words` and/or `stale_days` sweep of the store), bounded by `limit`, overwriting the cache;
per-word report with honest errors. Adds a `force_refresh` path to the engine + `KnowledgeStore.stale_words`.
**Nine MCP tools now** (only optional `validate_pure_tamil`/`generate_forms`/`transliterate` left from §6).
**79 tests pass** (77 without live foma). Design repo at `~/projects/thamizh-mcp-design/` →
`ief-global/thamizh-mcp-design` (blueprint, tamil-grammar.md, DECISIONS, roadmap, CODE-STATUS.md).

## Test ladder (run in order, from repo root)
```bash
uv sync                                              # installs deps incl. pytest
which flookup && echo "மரம்" | flookup data/fst/noun.fst
uv run pytest -v                                     # expect 79 passed with foma
uv run python scripts/analyze.py மரத்தில் --include formation  # பகுதி மரம் + சாரியை அத்து + விகுதி இல்
uv run python scripts/analyze.py ரயில் --include origin       # loanword: முதல் எழுத்து rule
uv run python scripts/analyze.py ஜோதி --include origin        # வடசொல்: Grantha letter
uv run python scripts/analyze.py மரத்தில்            # lemma மரம், loc|soc kept, Tholkappiyam cites
uv run python scripts/analyze.py புத்தகம் --include meaning   # first live Wiktionary pull
uv run python scripts/analyze.py புத்தகம் --include meaning   # again → must serve from cache
sqlite3 data/knowledge.sqlite3 'select word,field,source,tier,retrieved from claims;'
```
Register as an MCP server: `claude mcp add thamizh -- uv --directory ~/projects/thamizh-mcp run thamizh-mcp`

## Next tasks (build order)
1. ~~**Kalaichol / equivalents adapter** over the pinned I2PT CSVs →
   `suggest_native_equivalent`.~~ **DONE (2026-07-17):** local I2PT adapter +
   engine wiring + MCP tool + tests. **Remaining under this objective:** (a) mine
   ta.wiktionary `{{சொல்வளம்N|...}}` synonym templates as a second *network* evolving
   source (must honor `allow_enrichment`); (b) TVA govt கலைச்சொல் **anchor** glossary
   (`kalaichol.py` still a stub — network snapshot, see task 5).
2. ~~**Origin classifier** → four Tholkappiyam classes.~~ **DONE (2026-07-17):**
   `core/classifier.py` (open-tamil Grantha + Tholkappiyam முதல்/இறுதி எழுத்து rules +
   FST parse + I2PT), `classify_origin` tool, gates `native_equivalent`. **Remaining/deferred:**
   திரிசொல்/திசைச்சொல் need a lexical/dialectal corpus (return `unknown` for now, never guessed);
   Thamizhi Validator + a real loanword dataset can slot in later as stronger signals to lift
   the many honest `unknown`s (e.g. புத்தகம், கம்ப்யூட்டர்).
3. ~~**Remaining MCP tools:** classify_origin, get_root, get_meaning,
   suggest_native_equivalent, enrich_word, explain_formation, explain_grammar.~~
   **DONE + `refresh_sources` (2026-07-18) → 9 tools.** Only optional
   `validate_pure_tamil`/`generate_forms`/`transliterate` remain from blueprint §6.
4. ~~**Formation decoder** (FST tags → பகுபத உறுப்பு) — Phase 3.~~ **DONE (2026-07-18):**
   `decode_formation` + verb tense/முற்று grammar. **Deferred (honest boundary):** precise
   விகாரம்/சந்தி naming beyond the confident rules (e.g. verb root வா→வந்) — the FST doesn't hand
   the join over, so it's left unnamed for now, never invented.
5. **Phase 4 eval** (morphological lift, `thamizh-eval` skill — D-005), then Madras Lexicon +
   TVA கலைச்சொல் snapshots (pin in `data/`, network-open session). Also near-term:
   transaction logging (gold-corpus flywheel, `thamizh-data-curation` — blueprint §12) and
   `refresh_sources`. Program roadmap: `~/projects/thamizh-mcp-design/TAMIL-HIGH-RESOURCE-ROADMAP.md`.

## Design rules (do not violate)
- **Tholkappiyam-first:** cite Tholkappiyam before Nannool for grammar claims.
- **Self-enriching, no static dictionary:** fill gaps from live sources, cache
  per-claim with provenance (source + tier + retrieved date).
- **Honesty over guessing:** unknown → return a **gap**, never a fabricated answer.

## Gotchas
- Install package **`foma`**, NOT `foma-bin` (empty transitional deb).
- Wikimedia blocks default UAs → descriptive UA lives in the adapter
  (`THAMIZH_HTTP_UA` overrides).
- `--include meaning` skips morphology by design (empty lemma there is not a bug).
- `data/knowledge.sqlite3` is gitignored — the self-enriching cache is machine-local.
- Wiktionary text is CC BY-SA (share-alike): cache is fine for private testing,
  resolve licensing before distributing any cached text.

## Where things live
- Runbook: `TESTING-ON-LINUX.md` · Pins/citations: `data/PINS.md` · Demo CLI:
  `scripts/analyze.py` · Contract: `src/thamizh_mcp/schema.py`
- Design docs (Windows/E:\ only, not in repo): blueprint, hosting + distribution plans.
