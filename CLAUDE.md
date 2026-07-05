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

## Current state (2026-07-04)
**Phase 1 core DONE.** FastMCP server with `analyze_word` end-to-end: ThamizhiMorph
FST anchor (foma), SQLite per-claim knowledge store + self-enriching
pull→write-back→cache loop, Wiktionary adapter (descriptive UA + real ta.wiktionary
template-style parser). **27 tests pass** (25 without live foma).

## Test ladder (run in order, from repo root)
```bash
uv sync                                              # installs deps incl. pytest
which flookup && echo "மரம்" | flookup data/fst/noun.fst
uv run pytest -v                                     # expect 27 passed with foma
uv run python scripts/analyze.py மரத்தில்            # lemma மரம், loc|soc kept, Tholkappiyam cites
uv run python scripts/analyze.py புத்தகம் --include meaning   # first live Wiktionary pull
uv run python scripts/analyze.py புத்தகம் --include meaning   # again → must serve from cache
sqlite3 data/knowledge.sqlite3 'select word,field,source,tier,retrieved from claims;'
```
Register as an MCP server: `claude mcp add thamizh -- uv --directory ~/projects/thamizh-mcp run thamizh-mcp`

## Next tasks (build order)
1. **Kalaichol / equivalents adapter** over the pinned I2PT CSVs
   (`data/equivalents/`, 2,063 rows) → powers `suggest_native_equivalent`.
   Local data, buildable now. Also mine ta.wiktionary `{{சொல்வளம்N|...}}`
   synonym templates as an evolving equivalent source.
2. **Origin classifier** — Thamizhi Validator + I2PT + loanword data → four
   Tholkappiyam classes (இயற்சொல் / வடசொல் / …).
3. **Remaining MCP tools:** classify_origin, get_root, get_meaning,
   explain_formation, explain_grammar, suggest_native_equivalent, enrich_word
   (`analyze_word` already live).
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
