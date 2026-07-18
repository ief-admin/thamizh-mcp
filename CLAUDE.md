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
**Root + meaning tools live (2026-07-17):** thin `get_root` (FST lemma/POS, keeps all analyses)
and `get_meaning` (self-enriching store → Wiktionary pull, provenance-tagged) MCP heads over the
existing engine paths. **Five MCP tools now.** **55 tests pass** (53 without live foma).

## Test ladder (run in order, from repo root)
```bash
uv sync                                              # installs deps incl. pytest
which flookup && echo "மரம்" | flookup data/fst/noun.fst
uv run pytest -v                                     # expect 55 passed with foma
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
3. **Remaining MCP tools:** ~~classify_origin~~, ~~get_root~~, ~~get_meaning~~,
   ~~suggest_native_equivalent~~ done. **Left:** explain_formation, explain_grammar
   (both wait on the Phase-3 formation decoder), enrich_word (`analyze_word` already live).
4. **Formation decoder** (FST tags → பகுபத உறுப்பு) — Phase 3.
5. **Phase 4 eval**, then Madras Lexicon + TVA கலைச்சொல் snapshots (pin in `data/`).

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
